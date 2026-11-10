// Same-process exact-sample sharing. Endpoint/record fields follow the pinned
// BaiduPCS-Go source; online compatibility is unverified, not an official API
// entitlement. MD5 normalization adapts Apache-2.0 BaiduPCS-Go DecryptMD5.
package main

import (
	"context"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const sampleName = "GCF_000005845.2_ASM584v2_genomic.fna.gz"
const sampleSize = 1379902
const sampleMD5 = "c13d459b5caa702ff7e1f26fe44b8ad7"
const sampleSHA = "a96d3cfa58c88d477013c768f90a11d2386d42a70d566abfb6d9013dcbd24255"

type expectedSample struct {
	Task        string `json:"task"`
	Account     string `json:"account"`
	Application string `json:"application"`
	FSID        string `json:"fsid"`
	Path        string `json:"path"`
	Size        int64  `json:"size"`
	MD5         string `json:"md5"`
	SHA256      string `json:"sha256"`
	Mapping     string `json:"mapping_sha256"`
}
type sharePlan struct {
	Sample       expectedSample `json:"sample"`
	Period       int            `json:"period"`
	Code         string         `json:"code"`
	AllowHistory bool           `json:"allow_own_share_page"`
	IntentFD     int            `json:"intent_dir_fd"`
	ResultFD     int            `json:"private_result_fd"`
}

func positive(v interface{}) (string, bool) {
	n, ok := v.(json.Number)
	if !ok {
		return "", false
	}
	s := string(n)
	value, e := strconv.ParseInt(s, 10, 64)
	return s, e == nil && value > 0 && strconv.FormatInt(value, 10) == s
}
func integer(v interface{}) (int64, bool) {
	n, ok := v.(json.Number)
	if !ok {
		return 0, false
	}
	x, e := strconv.ParseInt(string(n), 10, 64)
	return x, e == nil && strconv.FormatInt(x, 10) == string(n)
}
func hashJSON(v interface{}) string {
	b, _ := json.Marshal(v)
	x := sha256.Sum256(b)
	return hex.EncodeToString(x[:])
}
func (e expectedSample) fields() map[string]interface{} {
	return map[string]interface{}{"task": e.Task, "account": e.Account, "application": e.Application, "fsid": e.FSID, "path": e.Path, "size": e.Size, "md5": e.MD5, "sha256": e.SHA256}
}
func (e expectedSample) valid() bool {
	_, ok := positive(json.Number(e.FSID))
	return ok && regexp.MustCompile(`^job-[0-9a-f]{32}$`).MatchString(e.Task) && e.Application == "Xtransfer" && strings.HasPrefix(e.Account, "sha256:") && digestPattern.MatchString(strings.TrimPrefix(e.Account, "sha256:")) && e.Path == "/apps/Xtransfer/mvp-validation/"+e.Task+"/"+sampleName && e.Size == sampleSize && e.MD5 == sampleMD5 && e.SHA256 == sampleSHA && e.Mapping == hashJSON(e.fields())
}
func (p sharePlan) valid() bool {
	return p.Sample.valid() && p.Period >= 1 && p.Period <= 7 && regexp.MustCompile(`^[a-z0-9]{4}$`).MatchString(p.Code) && p.AllowHistory && p.IntentFD >= 3 && p.ResultFD >= 3 && p.ResultFD != p.IntentFD
}
func (e expectedSample) key() string {
	x := sha256.Sum256([]byte(e.Account + ":" + e.FSID))
	return hex.EncodeToString(x[:])
}
func singleQuery(u *url.URL, expected map[string]string) bool {
	q, e := url.ParseQuery(u.RawQuery)
	if e != nil || len(q) != len(expected) {
		return false
	}
	for k, v := range expected {
		if len(q[k]) != 1 || q.Get(k) != v {
			return false
		}
	}
	return true
}
func shareRoutePermitted(method string, u *url.URL) bool {
	if u.Host != "pan.baidu.com" {
		return false
	}
	switch u.Path {
	case "/api/list":
		q, e := url.ParseQuery(u.RawQuery)
		if e != nil {
			return false
		}
		dir := q.Get("dir")
		if !regexp.MustCompile(`^/apps/Xtransfer/mvp-validation/job-[0-9a-f]{32}$`).MatchString(dir) {
			return false
		}
		return method == "GET" && singleQuery(u, map[string]string{"dir": dir, "order": "name", "desc": "0", "clienttype": "0", "num": "2", "page": "1"})
	case "/share/pset":
		return method == "POST" && u.RawQuery == ""
	case "/share/record":
		return method == "GET" && singleQuery(u, map[string]string{"page": "1", "desc": "1", "order": "time"})
	case "/share/surlinfoinrecord":
		q, e := url.ParseQuery(u.RawQuery)
		if e != nil {
			return false
		}
		id, ok := positive(json.Number(q.Get("shareid")))
		return ok && method == "GET" && singleQuery(u, map[string]string{"shareid": id, "sign": shareSign(id)})
	}
	return false
}
func shareSign(id string) string {
	x := md5.Sum([]byte(id + "_sharesurlinfo!@#"))
	return hex.EncodeToString(x[:])
}
func api(raw []byte) (map[string]interface{}, error) {
	m, e := object(raw)
	if e != nil {
		return nil, e
	}
	n, ok := integer(m["errno"])
	if !ok || n != 0 {
		return nil, rejected
	}
	return m, nil
}
func normalizedMD5(v interface{}) string {
	raw, ok := v.(string)
	if !ok || len(raw) != 32 {
		return ""
	}
	if regexp.MustCompile(`^[0-9a-fA-F]{32}$`).MatchString(raw) {
		return strings.ToLower(raw)
	}
	if raw[9] < 'g' || raw[9] > 'v' {
		return ""
	}
	value := raw[:9] + fmt.Sprintf("%x", raw[9]-'g') + raw[10:]
	if !regexp.MustCompile(`^[0-9a-f-]{32}$`).MatchString(value) {
		return ""
	}
	var out strings.Builder
	for i, c := range value {
		n := int64(0)
		if c != '-' {
			n, _ = strconv.ParseInt(string(c), 16, 8)
		}
		fmt.Fprintf(&out, "%x", n^int64(i&15))
	}
	x := out.String()
	return x[8:16] + x[:8] + x[24:] + x[16:24]
}
func exactObject(raw []byte, e expectedSample) bool {
	m, err := api(raw)
	if err != nil {
		return false
	}
	list, ok := m["list"].([]interface{})
	if !ok || len(list) != 1 {
		return false
	}
	row, ok := list[0].(map[string]interface{})
	if !ok {
		return false
	}
	id, idOK := positive(row["fs_id"])
	size, sizeOK := integer(row["size"])
	dir, dirOK := integer(row["isdir"])
	return idOK && id == e.FSID && row["path"] == e.Path && sizeOK && size == e.Size && dirOK && dir == 0 && normalizedMD5(row["md5"]) == e.MD5
}
func validLink(value interface{}) (string, bool) {
	s, ok := value.(string)
	if !ok || len(s) > 2048 || strings.ContainsAny(s, "\\\r\n\t ") {
		return "", false
	}
	u, e := url.Parse(s)
	if e != nil || u.Scheme != "https" || u.Host != "pan.baidu.com" || u.User != nil || u.Fragment != "" || u.RawPath != "" || strings.Contains(s, "#") {
		return "", false
	}
	if strings.HasPrefix(u.Path, "/s/") && regexp.MustCompile(`^[A-Za-z0-9_-]{6,128}$`).MatchString(strings.TrimPrefix(u.Path, "/s/")) && u.RawQuery == "" {
		return s, true
	}
	q := u.Query()
	return s, u.Path == "/netdisk/share" && singleQuery(u, map[string]string{"surl": q.Get("surl")}) && regexp.MustCompile(`^[A-Za-z0-9_-]{6,128}$`).MatchString(q.Get("surl"))
}
func parseCreated(raw []byte) (string, string, bool) {
	m, e := api(raw)
	if e != nil {
		return "", "", false
	}
	id, ok := positive(m["shareid"])
	link, good := validLink(m["link"])
	return id, link, ok && good
}
func matchRecord(raw []byte, p sharePlan, id, link string, elapsed time.Duration) bool {
	m, e := api(raw)
	if e != nil {
		return false
	}
	rows, ok := m["list"].([]interface{})
	if !ok || len(rows) > 128 {
		return false
	}
	seen := map[string]bool{}
	matches := 0
	for _, value := range rows {
		row, ok := value.(map[string]interface{})
		if !ok {
			return false
		}
		sid, good := positive(row["shareId"])
		if !good || seen[sid] {
			return false
		}
		seen[sid] = true
		if sid != id {
			continue
		}
		matches++
		ids, ok := row["fsIds"].([]interface{})
		if !ok || len(ids) != 1 {
			return false
		}
		fsid, good := positive(ids[0])
		pub, pubOK := integer(row["public"])
		kind, kindOK := integer(row["expiredType"])
		remaining, timeOK := integer(row["expiredTime"])
		expected := int64(p.Period) * 86400
		lower := expected - int64(elapsed.Seconds()) - 600
		if !good || fsid != p.Sample.FSID || row["typicalPath"] != p.Sample.Path || row["shortlink"] != link || !pubOK || pub != 0 || !kindOK || kind == -1 || !timeOK || remaining <= 0 || remaining > expected || remaining < lower {
			return false
		}
	}
	return matches == 1
}
func confirmPassword(raw []byte, want string) bool {
	m, e := api(raw)
	if e != nil {
		return false
	}
	pwd, ok := m["pwd"].(string)
	return ok && pwd == want
}

type shareLedger struct {
	dir  int
	lock *os.File
	name string
}

var consumed = errors.New("share_intent_already_consumed")

func openLedger(p sharePlan) (*shareLedger, error) {
	var st syscall.Stat_t
	if e := syscall.Fstat(p.IntentFD, &st); e != nil || st.Mode&syscall.S_IFMT != syscall.S_IFDIR || st.Uid != uint32(os.Geteuid()) || st.Mode&0077 != 0 {
		return nil, rejected
	}
	var dest syscall.Stat_t
	if e := syscall.Fstat(p.ResultFD, &dest); e != nil || dest.Mode&syscall.S_IFMT != syscall.S_IFIFO || dest.Uid != uint32(os.Geteuid()) {
		return nil, rejected
	}
	fd, e := syscall.Openat(p.IntentFD, p.Sample.key()+".lock", syscall.O_RDWR|syscall.O_CREAT|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0600)
	if e != nil {
		return nil, rejected
	}
	f := os.NewFile(uintptr(fd), "<private_intent_lock>")
	if e = syscall.Fstat(fd, &st); e != nil || st.Mode&syscall.S_IFMT != syscall.S_IFREG || st.Uid != uint32(os.Geteuid()) || st.Nlink != 1 || st.Mode&0077 != 0 {
		f.Close()
		return nil, rejected
	}
	if e = syscall.Flock(fd, syscall.LOCK_EX|syscall.LOCK_NB); e != nil {
		f.Close()
		return nil, e
	}
	l := &shareLedger{dir: p.IntentFD, lock: f, name: p.Sample.key() + ".json"}
	existing, e := syscall.Openat(l.dir, l.name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
	if e == nil {
		syscall.Close(existing)
		l.close()
		return nil, consumed
	}
	if e != syscall.ENOENT {
		l.close()
		return nil, rejected
	}
	return l, nil
}
func (l *shareLedger) close() {
	if l != nil && l.lock != nil {
		syscall.Flock(int(l.lock.Fd()), syscall.LOCK_UN)
		l.lock.Close()
		l.lock = nil
	}
}
func (l *shareLedger) record(p sharePlan, state, id string, initial bool) error {
	value := map[string]interface{}{"schema": 1, "binding_sha256": p.Sample.Mapping, "period": p.Period, "state": state, "recorded_utc": time.Now().UTC().Format(time.RFC3339), "automatic_replay_allowed": false}
	if id != "" {
		value["share_id"] = id
	}
	raw, _ := json.Marshal(value)
	name := l.name
	if !initial {
		name += ".update"
	}
	fd, e := syscall.Openat(l.dir, name, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0600)
	if e != nil {
		return rejected
	}
	f := os.NewFile(uintptr(fd), "<private_intent>")
	_, e = f.Write(raw)
	if e == nil {
		e = f.Sync()
	}
	closeErr := f.Close()
	if e != nil || closeErr != nil {
		return rejected
	}
	if !initial {
		if e = syscall.Renameat(l.dir, name, l.dir, l.name); e != nil {
			return rejected
		}
	}
	return syscall.Fsync(l.dir)
}
func privateResult(p sharePlan, link string) bool {
	raw, _ := json.Marshal(map[string]interface{}{"link": link, "code": p.Code, "period": p.Period})
	if len(raw) > 4096 {
		return false
	}
	if syscall.SetNonblock(p.ResultFD, true) != nil {
		return false
	}
	n, e := syscall.Write(p.ResultFD, raw)
	return e == nil && n == len(raw)
}
func (s *session) runShare(ctx context.Context, in input) report {
	s.result = report{Status: "share_plan_rejected_no_login", Phase: "validation"}
	p := in.Share
	if p == nil || !p.valid() {
		return s.result
	}
	ledger, e := openLedger(*p)
	if e != nil {
		if errors.Is(e, consumed) {
			s.result.Status = "share_intent_already_consumed_no_login"
		} else {
			s.result.Status = "share_intent_unavailable_no_login"
		}
		return s.result
	}
	defer ledger.close()
	in.Expected = strings.TrimPrefix(p.Sample.Account, "sha256:")
	s.run(ctx, in)
	if s.result.AuthCode == p.Code {
		s.result.AuthCode = "other"
	}
	defer func() { s.bduss = "" }()
	if s.result.Status != "session_identity_verified_no_persistence" || !s.result.ExpectedMatch {
		return s.result
	}
	params := url.Values{"dir": {path.Dir(p.Sample.Path)}, "order": {"name"}, "desc": {"0"}, "clienttype": {"0"}, "num": {"2"}, "page": {"1"}}
	raw, e := s.request(ctx, "sample_object", "GET", "https://pan.baidu.com/api/list?"+params.Encode(), nil, s.bduss)
	if e != nil || !exactObject(raw, p.Sample) {
		s.result.Status = "share_original_object_unverified"
		return s.result
	}
	s.result.OriginalObjectMatched = true
	s.result.IntentConsumed = true // Failed fsync may still leave a consumed file.
	if e = ledger.record(*p, "creation_outcome_unknown", "", true); e != nil {
		s.result.Status = "share_intent_write_failed"
		return s.result
	}
	s.result.IntentConsumed = true
	s.result.CreationUnknown = true
	s.result.Status = "share_creation_outcome_unknown"
	paths, _ := json.Marshal([]string{p.Sample.Path})
	form := url.Values{"path_list": {string(paths)}, "schannel": {"4"}, "channel_list": {"[]"}, "period": {strconv.Itoa(p.Period)}, "pwd": {p.Code}, "share_type": {"9"}}
	started := time.Now()
	s.result.ShareRequests = 1
	raw, e = s.request(ctx, "share_create", "POST", "https://pan.baidu.com/share/pset", form, s.bduss)
	if e != nil {
		return s.result
	}
	if m, err := object(raw); err == nil {
		if code, ok := integer(m["errno"]); ok && code != 0 {
			s.result.CreationUnknown = false
			s.result.Status = "share_creation_rejected"
			text := strconv.FormatInt(code, 10)
			if code >= -1000000 && code <= 1000000 && text != p.Code && text != in.Username && text != in.Password {
				s.result.ShareErrno = &code
			}
			_ = ledger.record(*p, "creation_rejected", "", false)
			return s.result
		}
	}
	id, link, ok := parseCreated(raw)
	if !ok {
		return s.result
	}
	s.result.CreationUnknown = false
	s.result.ShareCreated = true
	s.result.Status = "share_created_unverified"
	if ledger.record(*p, "created_unverified", id, false) != nil {
		return s.result
	}
	params = url.Values{"page": {"1"}, "desc": {"1"}, "order": {"time"}}
	s.result.HistoryRead = true
	raw, e = s.request(ctx, "share_record", "GET", "https://pan.baidu.com/share/record?"+params.Encode(), nil, s.bduss)
	if e != nil || !matchRecord(raw, *p, id, link, time.Since(started)) {
		s.result.Status = "share_record_unverified"
		return s.result
	}
	s.result.RecordMatched = true
	s.result.ExpiryBounded = true
	params = url.Values{"shareid": {id}, "sign": {shareSign(id)}}
	raw, e = s.request(ctx, "share_password", "GET", "https://pan.baidu.com/share/surlinfoinrecord?"+params.Encode(), nil, s.bduss)
	if e != nil || !confirmPassword(raw, p.Code) {
		s.result.Status = "share_password_unverified"
		return s.result
	}
	s.result.PasswordConfirmed = true
	if ledger.record(*p, "source_record_mapping_matched", id, false) != nil {
		return s.result
	}
	s.result.Status = "share_mapping_verified_private_result_failed"
	if !privateResult(*p, link) {
		return s.result
	}
	s.result.PrivateReady = true
	s.result.Status = "share_mapping_verified_private_result_ready"
	return s.result
}
