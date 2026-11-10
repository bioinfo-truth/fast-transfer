// One-attempt, in-memory login preparation; not an upstream release command.
// WAP form and RSA usage adapted from Baidu-Login v1.4.1 (MIT, Copyright iikira).
// No PCSConfig, Tieba initialization, credential export, persistence or sharing.
package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"errors"
	"github.com/qjfoidnh/Baidu-Login/bdcrypto"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

var rejected = errors.New("login_session_rejected")
var usernamePattern = regexp.MustCompile(`^[^\x00-\x1f\x7f]{1,256}$`)
var digestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
var clockPattern = regexp.MustCompile(`"time"\s*:\s*"([0-9a-fA-F]{8,32})"`)
var keyPattern = regexp.MustCompile(`,rsa:"([0-9a-fA-F]+)",error:`)

type input struct {
	Username    string `json:"username"`
	Password    string `json:"password"`
	Expected    string `json:"expected_account_sha256"`
	SessionOnly bool   `json:"session_only"`
}
type report struct {
	Status               string `json:"status"`
	Phase                string `json:"phase"`
	Requests             int    `json:"request_attempts"`
	AuthPosts            int    `json:"authentication_post_attempts"`
	AuthCode             string `json:"auth_code,omitempty"`
	SessionCookiePresent bool   `json:"session_cookie_received"`
	IdentityAccepted     bool   `json:"netdisk_identity_accepted"`
	ExpectedChecked      bool   `json:"expected_account_checked"`
	ExpectedMatch        bool   `json:"expected_account_matches"`
	CredentialsSaved     bool   `json:"credentials_saved"`
	ShareRequests        int    `json:"share_requests"`
	Closed               bool   `json:"closed"`
}

type session struct {
	client *http.Client
	result report
	trace  string
}

// Strict bounded JSON with duplicate keys rejected at every depth. Never returns
// a parse error containing input bytes; no remote errmsg is printed.
func object(raw []byte) (map[string]interface{}, error) {
	if len(raw) == 0 || len(raw) > 65536 {
		return nil, rejected
	}
	d := json.NewDecoder(strings.NewReader(string(raw)))
	d.UseNumber()
	nodes := 0
	var read func(int) (interface{}, error)
	read = func(depth int) (interface{}, error) {
		nodes++
		if depth > 12 || nodes > 2048 {
			return nil, rejected
		}
		token, e := d.Token()
		if e != nil {
			return nil, rejected
		}
		switch t := token.(type) {
		case json.Delim:
			if t == '{' {
				m := map[string]interface{}{}
				for d.More() {
					k, e := d.Token()
					if e != nil {
						return nil, rejected
					}
					key, ok := k.(string)
					if !ok || len(key) > 128 {
						return nil, rejected
					}
					if _, ok = m[key]; ok {
						return nil, rejected
					}
					v, e := read(depth + 1)
					if e != nil {
						return nil, e
					}
					m[key] = v
				}
				last, e := d.Token()
				if e != nil || last != json.Delim('}') {
					return nil, rejected
				}
				return m, nil
			}
			if t == '[' {
				a := []interface{}{}
				for d.More() {
					if len(a) > 128 {
						return nil, rejected
					}
					v, e := read(depth + 1)
					if e != nil {
						return nil, e
					}
					a = append(a, v)
				}
				last, e := d.Token()
				if e != nil || last != json.Delim(']') {
					return nil, rejected
				}
				return a, nil
			}
			return nil, rejected
		case string:
			if len(t) > 8192 {
				return nil, rejected
			}
		}
		return token, nil
	}
	v, e := read(0)
	if e != nil {
		return nil, e
	}
	if _, e = d.Token(); e != io.EOF {
		return nil, rejected
	}
	m, ok := v.(map[string]interface{})
	if !ok {
		return nil, rejected
	}
	return m, nil
}

func permitted(method string, u *url.URL) bool {
	if u == nil || u.Scheme != "https" || u.Port() != "" || u.User != nil || u.Fragment != "" || u.RawPath != "" {
		return false
	}
	if u.Host == "wappass.baidu.com" && u.RawQuery == "" {
		return method == "GET" && (u.Path == "/" || u.Path == "/wp/api/security/antireplaytoken" || u.Path == "/static/touch/js/login_d9bffc9.js") || method == "POST" && u.Path == "/wp/api/login"
	}
	return u.Host == "pan.baidu.com" && method == "GET" && u.Path == "/api/user/getinfo" && u.RawQuery == "need_selfinfo=1"
}

func productionClient() (*http.Client, *http.Transport) {
	// Fresh connections plus disabled keepalive prevent http.Transport's retry on
	// a reused connection. Proxy and environment proxy handling are absent.
	tr := &http.Transport{Proxy: nil, TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12}, DisableKeepAlives: true, DisableCompression: true, TLSHandshakeTimeout: 5 * time.Second, ResponseHeaderTimeout: 8 * time.Second}
	pins := map[string]string{}
	tr.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, e := net.SplitHostPort(address)
		if e != nil || port != "443" || (host != "wappass.baidu.com" && host != "pan.baidu.com") {
			return nil, rejected
		}
		target := pins[host]
		if target == "" {
			ips, e := net.DefaultResolver.LookupIPAddr(ctx, host)
			if e != nil || len(ips) == 0 {
				return nil, rejected
			}
			for _, ip := range ips {
				if !ip.IP.IsGlobalUnicast() || ip.IP.IsPrivate() || ip.IP.IsLoopback() || ip.IP.IsLinkLocalUnicast() {
					return nil, rejected
				}
			}
			target = ips[0].IP.String()
			pins[host] = target
		}
		return (&net.Dialer{Timeout: 5 * time.Second, KeepAlive: -1}).DialContext(ctx, "tcp", net.JoinHostPort(target, "443"))
	}
	jar, _ := cookiejar.New(nil)
	c := &http.Client{Transport: tr, Jar: jar, Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	return c, tr
}

func (s *session) request(ctx context.Context, phase, method, address string, body url.Values, bduss string) ([]byte, error) {
	u, e := url.Parse(address)
	if e != nil || !permitted(method, u) {
		return nil, rejected
	}
	s.result.Phase = phase
	s.result.Requests++
	var reader io.Reader
	if body != nil {
		reader = strings.NewReader(body.Encode())
	}
	req, e := http.NewRequestWithContext(ctx, method, address, reader)
	if e != nil {
		return nil, rejected
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 fast-transfer-login-session")
	req.Header.Set("Accept-Encoding", "identity")
	req.Header.Set("Accept", "application/json")
	if method == "POST" {
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("Referer", "https://wappass.baidu.com/")
		req.Header.Set("X-Requested-With", "XMLHttpRequest")
	}
	client := s.client
	if bduss != "" {
		if u.Host != "pan.baidu.com" || len(bduss) > 4096 || strings.ContainsAny(bduss, ";\r\n\t ") {
			return nil, rejected
		}
		// Netdisk receives only BDUSS, not the entire login-cookie jar.
		clone := *s.client
		clone.Jar = nil
		client = &clone
		req.Header.Set("Cookie", "BDUSS="+bduss)
	}
	response, e := client.Do(req)
	if e != nil {
		return nil, rejected
	}
	defer response.Body.Close()
	if phase == "bootstrap_trace" {
		trace := response.Header.Values("Trace-Id")
		if len(trace) != 1 || !regexp.MustCompile(`^[A-Za-z0-9_-]{1,256}$`).MatchString(trace[0]) {
			return nil, rejected
		}
		s.trace = trace[0]
	}
	if response.StatusCode != 200 || response.Header.Get("Content-Encoding") != "" && response.Header.Get("Content-Encoding") != "identity" {
		return nil, rejected
	}
	raw, e := io.ReadAll(io.LimitReader(response.Body, 65537))
	if e != nil || len(raw) > 65536 {
		return nil, rejected
	}
	return raw, nil
}

func validInput(v input) bool {
	return v.SessionOnly && usernamePattern.MatchString(v.Username) && len(v.Password) > 0 && len(v.Password) <= 512 && !strings.ContainsAny(v.Password, "\x00\r\n") && (v.Expected == "" || digestPattern.MatchString(v.Expected))
}

func (s *session) run(ctx context.Context, in input) report {
	s.result = report{Status: "input_rejected", Phase: "validation"}
	defer func() { s.client.Jar = nil }()
	if !validInput(in) {
		return s.result
	}
	s.result.Status = "bootstrap_failed_no_authentication"
	raw, e := s.request(ctx, "bootstrap_time", "GET", "https://wappass.baidu.com/wp/api/security/antireplaytoken", nil, "")
	if e != nil {
		return s.result
	}
	if _, e = object(raw); e != nil {
		return s.result
	}
	times := clockPattern.FindAllSubmatch(raw, -1)
	if len(times) != 1 {
		return s.result
	}
	clock := string(times[0][1])
	raw, e = s.request(ctx, "bootstrap_key", "GET", "https://wappass.baidu.com/static/touch/js/login_d9bffc9.js", nil, "")
	if e != nil {
		return s.result
	}
	keys := keyPattern.FindAllSubmatch(raw, -1)
	if len(keys) != 1 || (len(keys[0][1]) != 256 && len(keys[0][1]) != 512 && len(keys[0][1]) != 1024) {
		return s.result
	}
	key := string(keys[0][1])
	modulus, ok := new(big.Int).SetString(key, 16)
	if !ok || modulus.BitLen() < 1024 || modulus.Bit(0) != 1 || len([]byte(in.Password+clock)) >= len(key)/2 {
		return s.result
	}
	_, e = s.request(ctx, "bootstrap_trace", "GET", "https://wappass.baidu.com/", nil, "")
	if e != nil {
		return s.result
	}
	encrypted, e := bdcrypto.RSAEncryptOfWapBaidu(key, []byte(in.Password+clock))
	if e != nil {
		return s.result
	}
	form := loginForm(in.Username, encrypted, clock)
	form.Set("traceid", s.trace)
	// Single credential submission. Challenges and unexpected outcomes stop; no
	// SMS/email send, captcha fetch, loginProxy following or automatic retry.
	s.result.AuthPosts = 1
	s.result.Status = "authentication_outcome_unknown"
	raw, e = s.request(ctx, "login_post", "POST", "https://wappass.baidu.com/wp/api/login", form, "")
	form = nil
	if e != nil {
		return s.result
	}
	obj, e := object(raw)
	if e != nil {
		return s.result
	}
	info, ok := obj["errInfo"].(map[string]interface{})
	if !ok {
		return s.result
	}
	code, ok := info["no"].(string)
	if !ok || !regexp.MustCompile(`^[0-9-]{1,8}$`).MatchString(code) {
		return s.result
	}
	if code == in.Password || code == in.Username {
		s.result.AuthCode = "other"
	} else {
		s.result.AuthCode = code
	}
	if code != "0" {
		switch code {
		case "400023", "400101":
			s.result.Status = "phone_or_email_challenge_required_not_sent"
		case "500001", "500002":
			s.result.Status = "image_challenge_required_not_fetched"
		default:
			s.result.Status = "authentication_rejected"
		}
		return s.result
	}
	u, _ := url.Parse("https://wappass.baidu.com/")
	secret := ""
	for _, cookie := range s.client.Jar.Cookies(u) {
		if cookie.Name == "BDUSS" {
			if secret != "" {
				return s.result
			}
			secret = cookie.Value
		}
	}
	if len(secret) < 16 || len(secret) > 4096 || strings.ContainsAny(secret, ";\r\n\t \\\"") {
		s.result.Status = "success_code_without_session_cookie"
		return s.result
	}
	s.result.SessionCookiePresent = true
	s.result.Status = "login_created_identity_unverified"
	raw, e = s.request(ctx, "session_identity", "GET", "https://pan.baidu.com/api/user/getinfo?need_selfinfo=1", nil, secret)
	secret = ""
	if e != nil {
		return s.result
	}
	obj, e = object(raw)
	if e != nil {
		return s.result
	}
	errno, ok := obj["errno"].(json.Number)
	if !ok || errno != "0" {
		return s.result
	}
	rows, ok := obj["records"].([]interface{})
	if !ok || len(rows) != 1 {
		return s.result
	}
	row, ok := rows[0].(map[string]interface{})
	if !ok {
		return s.result
	}
	uk, ok := row["uk"].(json.Number)
	if !ok || !regexp.MustCompile(`^[1-9][0-9]{0,19}$`).MatchString(string(uk)) {
		return s.result
	}
	s.result.IdentityAccepted = true
	if in.Expected != "" {
		s.result.ExpectedChecked = true
		sum := sha256.Sum256([]byte(uk))
		s.result.ExpectedMatch = hex.EncodeToString(sum[:]) == in.Expected
		if !s.result.ExpectedMatch {
			s.result.Status = "account_mismatch"
			return s.result
		}
	}
	s.result.Status = "session_identity_verified_no_persistence"
	return s.result
}

func main() {
	result := report{Status: "input_rejected", Closed: true}
	defer func() {
		if recover() != nil {
			result = report{Status: "session_internal_failure", Closed: true}
		}
		_ = json.NewEncoder(os.Stdout).Encode(result)
	}()
	if len(os.Args) != 1 {
		return
	}
	st, e := os.Stdin.Stat()
	if e != nil || st.Mode()&os.ModeCharDevice != 0 {
		return
	}
	raw, e := io.ReadAll(io.LimitReader(os.Stdin, 8193))
	if e != nil || len(raw) > 8192 {
		return
	}
	obj, e := object(raw)
	if e != nil || len(obj) != 4 {
		return
	}
	var in input
	if e = json.Unmarshal(raw, &in); e != nil || !validInput(in) {
		return
	}
	for k := range obj {
		if k != "username" && k != "password" && k != "expected_account_sha256" && k != "session_only" {
			return
		}
	}
	client, tr := productionClient()
	defer tr.CloseIdleConnections()
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	s := &session{client: client}
	result = s.run(ctx, in)
	in.Password = ""
	raw = nil
	result.Closed = true
}
