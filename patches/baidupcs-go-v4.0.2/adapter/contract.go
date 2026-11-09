// Package pcsadapter validates wire candidates; it is NOT an authentication or
// network capability provider. Production PCS-Go entrypoints remain closed.
package pcsadapter

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

var (
	ErrShape   = errors.New("response_shape_rejected")
	ErrBinding = errors.New("scope_or_identity_mismatch")
	ErrState   = errors.New("terminal_or_invalid_state")
	ErrLive    = errors.New("live_entrypoint_closed")
)

const CookieNamespace = "cookie_netdisk_uk"

var opaqueID = regexp.MustCompile(`^[A-Za-z0-9_-]{1,128}$`)

var positive = regexp.MustCompile(`^[1-9][0-9]*$`)
var digest = regexp.MustCompile(`^[0-9a-f]{32}$`)
var password = regexp.MustCompile(`^[a-z0-9]{4}$`)
var shortID = regexp.MustCompile(`^[A-Za-z0-9_-]{6,128}$`)

type Owner struct{ Namespace, ID string }
type Scope struct {
	Task, Session, Path, FSID, MD5 string
	Owner                          Owner
	Size                           int64
	Expires                        time.Time
}

// No arbitrary decoder can create these sealed candidate fields through JSON.
type Principal struct {
	owner        Owner
	session      string
	scopeBinding [32]byte
	expires      time.Time
}
type Object struct{ binding [32]byte }
type Share struct{ id, link string }

func (s Share) Format(w fmt.State, v rune) { io.WriteString(w, "<private_share_candidate>") }
func (s Share) String() string             { return "<private_share_candidate>" }
func LiveConnect() error                   { return ErrLive }

func number(v interface{}, allowZero bool) (string, bool) {
	n, ok := v.(json.Number)
	if !ok {
		return "", false
	}
	s := string(n)
	if allowZero && s == "0" {
		return s, true
	}
	if !positive.MatchString(s) {
		return "", false
	}
	_, err := strconv.ParseInt(s, 10, 64)
	return s, err == nil
}

// Recursive token parsing rejects duplicate keys at ANY depth and extra JSON.
func strict(raw []byte) (map[string]interface{}, error) {
	if len(raw) == 0 || len(raw) > 65536 {
		return nil, ErrShape
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.UseNumber()
	nodes := 0
	var read func(int) (interface{}, error)
	read = func(depth int) (interface{}, error) {
		nodes++
		if depth > 16 || nodes > 2048 {
			return nil, ErrShape
		}
		t, err := d.Token()
		if err != nil {
			return nil, ErrShape
		}
		switch x := t.(type) {
		case json.Delim:
			if x == '{' {
				m := map[string]interface{}{}
				for d.More() {
					k, e := d.Token()
					if e != nil {
						return nil, ErrShape
					}
					key, ok := k.(string)
					if !ok || len(key) > 8192 {
						return nil, ErrShape
					}
					if _, exists := m[key]; exists {
						return nil, ErrShape
					}
					v, e := read(depth + 1)
					if e != nil {
						return nil, e
					}
					m[key] = v
				}
				end, e := d.Token()
				if e != nil || end != json.Delim('}') {
					return nil, ErrShape
				}
				return m, nil
			}
			if x == '[' {
				a := []interface{}{}
				for d.More() {
					if len(a) >= 128 {
						return nil, ErrShape
					}
					v, e := read(depth + 1)
					if e != nil {
						return nil, e
					}
					a = append(a, v)
				}
				end, e := d.Token()
				if e != nil || end != json.Delim(']') {
					return nil, ErrShape
				}
				return a, nil
			}
			return nil, ErrShape
		case string:
			if len(x) > 8192 {
				return nil, ErrShape
			}
			return x, nil
		default:
			return t, nil
		}
	}
	value, err := read(0)
	if err != nil {
		return nil, ErrShape
	}
	if _, e := d.Token(); e != io.EOF {
		return nil, ErrShape
	}
	m, ok := value.(map[string]interface{})
	if !ok {
		return nil, ErrShape
	}
	zero, ok := number(m["errno"], true)
	if !ok || zero != "0" {
		return nil, ErrShape
	}
	return m, nil
}
func canonicalPath(p string) bool {
	if !utf8.ValidString(p) || len(p) > 4096 {
		return false
	}
	for _, r := range p {
		if unicode.IsControl(r) {
			return false
		}
	}
	if !strings.HasPrefix(p, "/apps/Xtransfer/") || strings.ContainsAny(p, "\\\r\n\x00") || strings.Contains(p, "//") || strings.HasSuffix(p, "/") {
		return false
	}
	for _, part := range strings.Split(p, "/") {
		if part == "." || part == ".." {
			return false
		}
	}
	return true
}
func validScope(s Scope, now time.Time) bool {
	_, idOK := number(json.Number(s.Owner.ID), false)
	_, fileOK := number(json.Number(s.FSID), false)
	return opaqueID.MatchString(s.Task) && opaqueID.MatchString(s.Session) && s.Owner.Namespace == CookieNamespace && idOK && fileOK && s.Size > 0 && digest.MatchString(s.MD5) && canonicalPath(s.Path) && s.Expires.After(now) && !s.Expires.After(now.Add(5*time.Minute))
}
func ParseIdentity(raw []byte, s Scope, now time.Time) (Principal, error) {
	if !validScope(s, now) {
		return Principal{}, ErrBinding
	}
	m, e := strict(raw)
	if e != nil {
		return Principal{}, e
	}
	records, ok := m["records"].([]interface{})
	if !ok || len(records) != 1 {
		return Principal{}, ErrShape
	}
	r, ok := records[0].(map[string]interface{})
	if !ok {
		return Principal{}, ErrShape
	}
	id, ok := number(r["uk"], false)
	if !ok {
		return Principal{}, ErrShape
	}
	if id != s.Owner.ID {
		return Principal{}, ErrBinding
	}
	return Principal{owner: s.Owner, session: s.Session, scopeBinding: binding(s), expires: s.Expires}, nil
}
func binding(s Scope) [32]byte {
	// Length-delimited JSON avoids ambiguous concatenation. Scope has no secrets.
	b, _ := json.Marshal([]interface{}{s.Task, s.Session, s.Owner.Namespace, s.Owner.ID, s.Path, s.FSID, s.Size, s.MD5, s.Expires.UnixNano()})
	return sha256.Sum256(b)
}
func ParseObject(raw []byte, p Principal, s Scope, now time.Time) (Object, error) {
	if !validScope(s, now) || p.owner != s.Owner || p.session != s.Session || p.scopeBinding != binding(s) || !p.expires.After(now) {
		return Object{}, ErrBinding
	}
	m, e := strict(raw)
	if e != nil {
		return Object{}, e
	}
	list, ok := m["list"].([]interface{})
	if !ok {
		return Object{}, ErrShape
	}
	seenID := map[string]bool{}
	seenPath := map[string]bool{}
	found := false
	for _, v := range list {
		r, ok := v.(map[string]interface{})
		if !ok {
			return Object{}, ErrShape
		}
		id, ok := number(r["fs_id"], false)
		if !ok {
			return Object{}, ErrShape
		}
		path, ok := r["path"].(string)
		if !ok || seenID[id] || seenPath[path] {
			return Object{}, ErrShape
		}
		seenID[id] = true
		seenPath[path] = true
		if id == s.FSID || path == s.Path {
			size, ok := number(r["size"], false)
			isdir, dirOK := number(r["isdir"], true)
			md5, hashOK := r["md5"].(string)
			if !ok || !dirOK || isdir != "0" || !hashOK || md5 != s.MD5 || id != s.FSID || path != s.Path || size != strconv.FormatInt(s.Size, 10) {
				return Object{}, ErrBinding
			}
			found = true
		}
	}
	if !found {
		return Object{}, ErrBinding
	}
	return Object{binding: binding(s)}, nil
}
func ParseShare(raw []byte) (Share, error) {
	m, e := strict(raw)
	if e != nil {
		return Share{}, e
	}
	id, ok := number(m["shareid"], false)
	if !ok {
		return Share{}, ErrShape
	}
	link, ok := m["link"].(string)
	if !ok || len(link) > 2048 || strings.ContainsAny(link, "\\\r\n\t ") {
		return Share{}, ErrShape
	}
	u, e := url.Parse(link)
	if e != nil || u.Scheme != "https" || u.Hostname() != "pan.baidu.com" || u.User != nil || u.Fragment != "" || strings.Contains(link, "#") || u.ForceQuery || u.Port() != "" || u.EscapedPath() != u.Path {
		return Share{}, ErrShape
	}
	good := strings.HasPrefix(u.Path, "/s/") && shortID.MatchString(strings.TrimPrefix(u.Path, "/s/")) && u.RawQuery == ""
	if u.Path == "/netdisk/share" {
		q, err := url.ParseQuery(u.RawQuery)
		good = err == nil && len(q) == 1 && len(q["surl"]) == 1 && shortID.MatchString(q.Get("surl"))
	}
	if !good {
		return Share{}, ErrShape
	}
	return Share{id: id, link: link}, nil
}

// FixtureLedger exercises contract ordering; it has no transport, no persistence,
// no credentials, no cancellation API, and can NEVER confer live eligibility.
type FixtureLedger struct {
	s      Scope
	state  string
	share  Share
	period int
}

func NewFixtureLedger(s Scope, now time.Time) (*FixtureLedger, error) {
	if !strings.HasPrefix(s.Task, "fixture-") || !validScope(s, now) {
		return nil, ErrBinding
	}
	return &FixtureLedger{s: s, state: "ready_fixture"}, nil
}
func (l *FixtureLedger) Begin(o Object, period int, pwd string, now time.Time) error {
	if l.state != "ready_fixture" {
		return ErrState
	}
	if !validScope(l.s, now) || o.binding != binding(l.s) || period != 7 || !password.MatchString(pwd) {
		return ErrBinding
	}
	l.period = period
	l.state = "creation_unknown_fixture"
	return nil
}
func (l *FixtureLedger) Observe(raw []byte) error {
	if l.state != "creation_unknown_fixture" {
		return ErrState
	}
	s, e := ParseShare(raw)
	if e != nil {
		return e
	}
	l.share = s
	l.state = "created_unverified_fixture"
	return nil
}

// Mapping is a future adapter's attestation input, NOT a documented API envelope.
type Mapping struct {
	Owner                        Owner
	Session, ShareID, FSID, Path string
	Period                       int
}

func (l *FixtureLedger) Confirm(m Mapping, now time.Time) error {
	if l.state != "created_unverified_fixture" {
		return ErrState
	}
	if !validScope(l.s, now) || m.Owner != l.s.Owner || m.Session != l.s.Session || m.ShareID != l.share.id || m.FSID != l.s.FSID || m.Path != l.s.Path || m.Period != l.period {
		l.state = "quarantined_fixture"
		return ErrBinding
	}
	l.state = "verified_fixture"
	return nil
}
func (l *FixtureLedger) Stop()              { l.state = "stopped_fixture"; l.share = Share{} }
func (l *FixtureLedger) State() string      { return l.state }
func (l *FixtureLedger) LiveEligible() bool { return false }

// Fingerprint is non-secret evidence binding, not authentication proof.
func (o Object) Fingerprint() string { return hex.EncodeToString(o.binding[:]) }
