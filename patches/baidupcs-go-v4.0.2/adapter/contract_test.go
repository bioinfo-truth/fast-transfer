package pcsadapter

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"syscall"
	"testing"
	"time"
)

var when = time.Date(2026, 11, 9, 0, 0, 0, 0, time.UTC)

func scope() Scope {
	return Scope{Task: "fixture-task", Session: "fixture-session", Path: "/apps/Xtransfer/offline-fixture/synthetic.fna.gz", FSID: "501", MD5: strings.Repeat("a", 32), Owner: Owner{CookieNamespace, "101"}, Size: 1379902, Expires: when.Add(4 * time.Minute)}
}

var identity = []byte(`{"errno":0,"records":[{"uk":101}]}`)
var object = []byte(`{"errno":0,"list":[{"fs_id":501,"path":"/apps/Xtransfer/offline-fixture/synthetic.fna.gz","size":1379902,"isdir":0,"md5":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}`)
var share = []byte(`{"errno":0,"shareid":701,"link":"https://pan.baidu.com/s/FAKE_ONLY_001"}`)

func ready(t *testing.T) (Scope, Object, *FixtureLedger) {
	t.Helper()
	s := scope()
	p, e := ParseIdentity(identity, s, when)
	if e != nil {
		t.Fatal(e)
	}
	o, e := ParseObject(object, p, s, when)
	if e != nil {
		t.Fatal(e)
	}
	l, e := NewFixtureLedger(s, when)
	if e != nil {
		t.Fatal(e)
	}
	return s, o, l
}
func mapping(s Scope) Mapping {
	return Mapping{Owner: s.Owner, Session: s.Session, ShareID: "701", FSID: s.FSID, Path: s.Path, Period: 7}
}
func TestFTStrictIdentityRejectsSourceGaps(t *testing.T) {
	for _, raw := range []string{`{"records":[{"uk":101}]}`, `{"errno":0,"records":[{"uk":0}]}`, `{"errno":0,"records":[{"uk":-1}]}`, `{"errno":0,"records":[{"uk":"101"}]}`, `{"errno":false,"records":[{"uk":101}]}`, `{"errno":-6,"records":[]}`, `{"errno":0,"records":[{"uk":101},{"uk":101}]}`, `{"errno":0,"records":[{"uk":9223372036854775808}]}`} {
		if _, err := ParseIdentity([]byte(raw), scope(), when); err == nil {
			t.Fatal("unsafe identity accepted")
		}
	}
}
func TestFTDuplicateTrailingAndBudgetRejected(t *testing.T) {
	for _, raw := range []string{`{"errno":1,"errno":0,"records":[{"uk":101}]}`, `{"errno":0,"records":[{"uk":102,"uk":101}]}`, string(identity) + `{}`, string(identity) + ` false`, strings.Repeat(" ", 65537), `{"errno":0,"records":[{"uk":101}],"` + strings.Repeat("k", 8193) + `":0}`, `{"errno":0,"records":` + strings.Repeat("[", 20) + strings.Repeat("]", 20) + `}`} {
		if _, err := ParseIdentity([]byte(raw), scope(), when); err == nil {
			t.Fatal("ambiguous JSON accepted")
		}
	}
}
func TestFTExpectedOwnerSessionNamespaceAndExpiry(t *testing.T) {
	for _, change := range []func(*Scope){func(s *Scope) { s.Owner.ID = "102" }, func(s *Scope) { s.Owner.Namespace = "oauth_uk" }, func(s *Scope) { s.Session = "" }, func(s *Scope) { s.Session = "bad\nvalue" }, func(s *Scope) { s.Task = string([]byte{255}) }, func(s *Scope) { s.Expires = when }, func(s *Scope) { s.Expires = when.Add(6 * time.Minute) }, func(s *Scope) { s.Path = "/apps/Xtransfer/../other/file" }} {
		s := scope()
		change(&s)
		if _, err := ParseIdentity(identity, s, when); err == nil {
			t.Fatal("identity binding accepted")
		}
	}
}
func TestFTExactObjectBoundAcrossTaskAndSession(t *testing.T) {
	s, o, l := ready(t)
	if o.Fingerprint() == strings.Repeat("0", 64) {
		t.Fatal("empty object evidence")
	}
	for _, change := range []func(*Scope){func(s *Scope) { s.Task = "fixture-other" }, func(s *Scope) { s.Session = "fixture-other" }, func(s *Scope) { s.FSID = "502" }, func(s *Scope) { s.Path += ".other" }} {
		drift := s
		change(&drift)
		other, _ := NewFixtureLedger(drift, when)
		if other.Begin(o, 7, "f1a2", when) == nil {
			t.Fatal("object replay accepted")
		}
	}
	if l.Begin(o, 7, "f1a2", when) != nil {
		t.Fatal("fixture binding rejected")
	}
}
func TestFTObjectMismatchAndDuplicateRejected(t *testing.T) {
	s := scope()
	p, _ := ParseIdentity(identity, s, when)
	for _, raw := range []string{strings.Replace(string(object), `"fs_id":501`, `"fs_id":502`, 1), strings.Replace(string(object), `"size":1379902`, `"size":1379903`, 1), strings.Replace(string(object), `"isdir":0`, `"isdir":1`, 1), strings.Replace(string(object), `aaaaaaaa`, `bbbbbbbb`, 1), strings.Replace(string(object), `}]}`, `},`+strings.Split(string(object), `"list":[`)[1], 1)} {
		if _, err := ParseObject([]byte(raw), p, s, when); err == nil {
			t.Fatal("wrong object accepted")
		}
	}
	if _, err := ParseObject(object, Principal{}, s, when); err == nil {
		t.Fatal("unbound principal accepted")
	}
}
func TestFTShareRejectsMissingFieldsAndUnsafeURL(t *testing.T) {
	for _, raw := range []string{`{"link":"https://pan.baidu.com/s/FAKE_ONLY_001"}`, `{"errno":0,"shareid":0,"link":"https://pan.baidu.com/s/FAKE_ONLY_001"}`, `{"errno":0,"shareid":701,"link":"javascript:FAKE_ONLY"}`, strings.Replace(string(share), "pan.baidu.com/", "pan.baidu.com.evil.invalid/", 1), strings.Replace(string(share), "https://", "http://", 1), strings.Replace(string(share), "https://", "https://name@", 1), strings.Replace(string(share), "FAKE_ONLY_001", "FAKE_ONLY_001#", 1), strings.Replace(string(share), "FAKE_ONLY_001", "FAKE_ONLY_001?", 1), strings.Replace(string(share), "FAKE_ONLY_001", "FAKE_ONLY_001?pwd=f1a2", 1)} {
		if _, err := ParseShare([]byte(raw)); err == nil {
			t.Fatal("unsafe share accepted")
		}
	}
}
func TestFTShareOutputRedacted(t *testing.T) {
	s, e := ParseShare(share)
	if e != nil {
		t.Fatal(e)
	}
	if text := fmt.Sprintf("%v %+v %#v %s", s, s, s, s); strings.Contains(text, "FAKE_ONLY") {
		t.Fatal("link leaked in formatting")
	}
	b, _ := json.Marshal(s)
	if bytes.Contains(b, []byte("FAKE_ONLY")) {
		t.Fatal("link serialized")
	}
}
func TestFTUnknownCreationConsumesIntentAndNoRetry(t *testing.T) {
	_, o, l := ready(t)
	if l.Begin(o, 7, "f1a2", when) != nil {
		t.Fatal("begin")
	}
	if l.State() != "creation_unknown_fixture" {
		t.Fatal("unknown not retained")
	}
	if l.Observe([]byte(`{"errno":0}`)) == nil {
		t.Fatal("malformed ack accepted")
	}
	if l.Begin(o, 7, "f1a2", when) == nil {
		t.Fatal("unknown creation replay")
	}
	if l.Observe(share) != nil || l.State() != "created_unverified_fixture" {
		t.Fatal("ack parse")
	}
	if l.Observe(share) == nil {
		t.Fatal("duplicate ack")
	}
}
func TestFTMappingMismatchQuarantinesAndNoLiveEligibility(t *testing.T) {
	s, o, l := ready(t)
	l.Begin(o, 7, "f1a2", when)
	l.Observe(share)
	bad := mapping(s)
	bad.FSID = "502"
	if l.Confirm(bad, when) == nil || l.State() != "quarantined_fixture" {
		t.Fatal("mapping conflict not quarantined")
	}
	if l.Confirm(mapping(s), when) == nil {
		t.Fatal("quarantine cleared")
	}
	if l.LiveEligible() || LiveConnect() != ErrLive {
		t.Fatal("live allowed")
	}
}
func TestFTFixtureSuccessRemainsOfflineAndStopTerminal(t *testing.T) {
	s, o, l := ready(t)
	l.Begin(o, 7, "f1a2", when)
	l.Observe(share)
	if l.Confirm(mapping(s), when) != nil || l.State() != "verified_fixture" || l.LiveEligible() {
		t.Fatal("fixture/live separation")
	}
	l.Stop()
	if l.Begin(o, 7, "f1a2", when) == nil || l.Observe(share) == nil || l.Confirm(mapping(s), when) == nil {
		t.Fatal("stop replay")
	}
}
func TestFTPasswordPeriodAndFreshness(t *testing.T) {
	for _, v := range []struct {
		days int
		pwd  string
	}{{0, "f1a2"}, {7, "ABCD"}, {7, "abc"}} {
		_, o, l := ready(t)
		if l.Begin(o, v.days, v.pwd, when) == nil {
			t.Fatal("unsafe parameters")
		}
	}
	s, o, l := ready(t)
	if l.Begin(o, 7, "f1a2", s.Expires) == nil {
		t.Fatal("stale intent")
	}
}
func TestFTRuntimeBoundaries(t *testing.T) {
	for _, p := range []string{os.Getenv("FT_OUTSIDE_CANARY"), os.Getenv("FT_CANARY_SYMLINK")} {
		if p == "" {
			t.Fatal("missing probe")
		}
		if b, e := os.ReadFile(p); e == nil || b != nil {
			t.Fatal("outside read")
		}
	}
	fd, e := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, 0)
	if e == nil {
		syscall.Close(fd)
		t.Fatal("network allowed")
	}
	if e != syscall.EPERM {
		t.Fatal("wrong network error")
	}
}

func TestFTPrincipalCannotBeReboundOrExtended(t *testing.T) {
	s := scope()
	p, e := ParseIdentity(identity, s, when)
	if e != nil {
		t.Fatal(e)
	}
	for _, change := range []func(*Scope){func(s *Scope) { s.Task = "fixture-other" }, func(s *Scope) { s.Expires = s.Expires.Add(30 * time.Second) }, func(s *Scope) { s.Size++ }} {
		other := s
		change(&other)
		if _, e := ParseObject(object, p, other, when); e == nil {
			t.Fatal("principal scope changed")
		}
	}
	if _, e := ParseObject(object, p, s, s.Expires); e == nil {
		t.Fatal("stale principal")
	}
}
func TestFTMappingAllFieldsAndExpiry(t *testing.T) {
	for _, change := range []func(*Mapping){func(m *Mapping) { m.Owner.ID = "102" }, func(m *Mapping) { m.Owner.Namespace = "oauth_uk" }, func(m *Mapping) { m.Session = "other" }, func(m *Mapping) { m.ShareID = "702" }, func(m *Mapping) { m.Path += ".other" }, func(m *Mapping) { m.Period = 0 }} {
		s, o, l := ready(t)
		l.Begin(o, 7, "f1a2", when)
		l.Observe(share)
		m := mapping(s)
		change(&m)
		if l.Confirm(m, when) == nil || l.State() != "quarantined_fixture" {
			t.Fatal("mapping drift accepted")
		}
	}
	s, o, l := ready(t)
	l.Begin(o, 7, "f1a2", when)
	l.Observe(share)
	if l.Confirm(mapping(s), s.Expires) == nil {
		t.Fatal("expired mapping")
	}
}
func TestFTNonFixtureLedgerAndForgedObjectRejected(t *testing.T) {
	s := scope()
	s.Task = "ordinary-task"
	if _, e := NewFixtureLedger(s, when); e == nil {
		t.Fatal("ordinary task granted fixture writer")
	}
	_, _, l := ready(t)
	if l.Begin(Object{}, 7, "f1a2", when) == nil {
		t.Fatal("empty evidence")
	}
}
