package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"testing"
)

type fakeRT struct {
	cookie   string
	identity string
	t        *testing.T
	calls    []*http.Request
	fail     string
	auth     string
	key      string
	trace    string
}

func (f *fakeRT) RoundTrip(r *http.Request) (*http.Response, error) {
	f.calls = append(f.calls, r)
	if !permitted(r.Method, r.URL) {
		f.t.Fatal("unexpected destination")
	}
	if r.URL.Path == f.fail {
		return nil, rejected
	}
	text := ""
	h := http.Header{}
	status := 200
	switch r.URL.Path {
	case "/wp/api/security/antireplaytoken":
		text = `{"ok":true,"time":"e362bacbae"}`
	case "/static/touch/js/login_d9bffc9.js":
		text = `,rsa:"` + strings.Repeat("b", 256) + `",error:`
		if f.key != "" {
			text = f.key
		}
	case "/":
		text = "public page"
		h.Set("Trace-Id", "SYNTHETIC_TRACE")
		if f.trace == "missing" {
			h.Del("Trace-Id")
		}
	case "/wp/api/login":
		data, _ := io.ReadAll(r.Body)
		form, e := url.ParseQuery(string(data))
		if e != nil || form.Get("password") == "SYNTHETIC_PASSWORD" || form.Get("username") != "SYNTHETIC_USER" || form.Get("traceid") != "SYNTHETIC_TRACE" {
			f.t.Fatal("incorrect private form")
		}
		text = `{"errInfo":{"no":"0"}}`
		h.Add("Set-Cookie", "BDUSS=SYNTHETIC_SESSION_ONLY; Domain=baidu.com; Path=/; Secure")
		h.Add("Set-Cookie", "PTOKEN=SYNTHETIC_EXTRA; Domain=baidu.com; Path=/; Secure")
		if f.cookie != "" {
			h.Del("Set-Cookie")
			if f.cookie != "none" {
				h.Add("Set-Cookie", "BDUSS="+f.cookie+"; Domain=baidu.com; Path=/; Secure")
			}
		}
		if f.auth != "" {
			text = f.auth
		}
		if f.auth == "redirect" {
			status = 302
			h.Set("Location", "https://other.invalid/")
		}
	case "/api/user/getinfo":
		if r.Header.Get("Cookie") != "BDUSS=SYNTHETIC_SESSION_ONLY" {
			f.t.Fatal("excess cookie forwarding")
		}
		text = `{"errno":0,"records":[{"uk":3003}]}`
		if f.identity != "" {
			text = f.identity
		}
	default:
		f.t.Fatal("unreviewed path")
	}
	var body io.ReadCloser = io.NopCloser(strings.NewReader(text))
	if f.trace == "body_unread" && r.URL.Path == "/" {
		body = io.NopCloser(failingBody{})
	}
	return &http.Response{StatusCode: status, Header: h, Body: body, Request: r}, nil
}
func fixture(t *testing.T) (*session, *fakeRT) {
	f := &fakeRT{t: t}
	j, _ := cookiejar.New(nil)
	return &session{client: &http.Client{Transport: f, Jar: j, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, f
}
func credentials() input {
	return input{Username: "SYNTHETIC_USER", Password: "SYNTHETIC_PASSWORD", SessionOnly: true}
}
func TestSuccessfulSessionHasNoPersistenceOrSecretOutput(t *testing.T) {
	s, f := fixture(t)
	v := credentials()
	sum := sha256.Sum256([]byte("3003"))
	v.Expected = hex.EncodeToString(sum[:])
	r := s.run(context.Background(), v)
	if r.Status != "session_identity_verified_no_persistence" || !r.ExpectedMatch || len(f.calls) != 5 || r.AuthPosts != 1 || s.client.Jar != nil {
		t.Fatalf("bad result %+v", r)
	}
	raw, _ := json.Marshal(r)
	for _, secret := range []string{"SYNTHETIC_USER", "SYNTHETIC_PASSWORD", "SYNTHETIC_SESSION_ONLY", "SYNTHETIC_EXTRA", "3003"} {
		if strings.Contains(string(raw), secret) {
			t.Fatal("private output")
		}
	}
}
func TestBootstrapFailuresNeverSubmitCredentials(t *testing.T) {
	for _, path := range []string{"/wp/api/security/antireplaytoken", "/static/touch/js/login_d9bffc9.js", "/"} {
		s, f := fixture(t)
		f.fail = path
		r := s.run(context.Background(), credentials())
		if r.AuthPosts != 0 {
			t.Fatal("submitted after bootstrap failure")
		}
	}
	s, f := fixture(t)
	f.key = "no fresh key"
	if s.run(context.Background(), credentials()).AuthPosts != 0 {
		t.Fatal("key fallback")
	}
	s, f = fixture(t)
	f.trace = "missing"
	if s.run(context.Background(), credentials()).AuthPosts != 0 {
		t.Fatal("trace fallback")
	}
}
func TestAuthenticationUnknownIsNeverRetried(t *testing.T) {
	s, f := fixture(t)
	f.fail = "/wp/api/login"
	r := s.run(context.Background(), credentials())
	if r.AuthPosts != 1 || len(f.calls) != 4 || r.Status != "authentication_outcome_unknown" {
		t.Fatal("retry or wrong classification")
	}
}
func TestChallengesStopWithoutCodeSendOrResponseURL(t *testing.T) {
	for _, code := range []string{"400023", "400101", "500001", "500002", "400408"} {
		s, f := fixture(t)
		f.auth = `{"errInfo":{"no":"` + code + `","msg":"SYNTHETIC_SECRET"},"data":{"verifyUrl":"https://other.invalid/"}}`
		r := s.run(context.Background(), credentials())
		if r.AuthPosts != 1 || len(f.calls) != 4 || r.IdentityAccepted {
			t.Fatal("challenge followed")
		}
		b, _ := json.Marshal(r)
		if strings.Contains(string(b), "SYNTHETIC_SECRET") {
			t.Fatal("remote message echoed")
		}
	}
}
func TestRedirectAndUnknownEnvelopesFailClosed(t *testing.T) {
	for _, body := range []string{"redirect", `{"errInfo":{"no":"0","no":"0"}}`, `{"errInfo":{"no":0}}`, strings.Repeat("x", 65537)} {
		s, f := fixture(t)
		f.auth = body
		r := s.run(context.Background(), credentials())
		if r.IdentityAccepted || len(f.calls) != 4 {
			t.Fatal("accepted or redirected")
		}
	}
}
func TestIdentityMismatchNotDeclaredMatch(t *testing.T) {
	s, _ := fixture(t)
	v := credentials()
	v.Expected = strings.Repeat("a", 64)
	r := s.run(context.Background(), v)
	if r.Status != "account_mismatch" || r.ExpectedMatch {
		t.Fatal("mismatch ignored")
	}
}
func TestOnlyFixedHTTPSRoutes(t *testing.T) {
	for _, address := range []string{"http://wappass.baidu.com/wp/api/login", "https://wappass.baidu.com:443/wp/api/login", "https://wappass.baidu.com/wp/api/login?extra=x", "https://pan.baidu.com/share/pset", "https://tieba.baidu.com/c/s/login", "https://wappass.baidu.com/wp/api/login#x"} {
		u, _ := url.Parse(address)
		if permitted("POST", u) {
			t.Fatal("route allowed")
		}
	}
}
func TestProductionTransportHasNoProxyTLSBypassOrReuse(t *testing.T) {
	c, tr := productionClient()
	defer tr.CloseIdleConnections()
	if tr.Proxy != nil || tr.TLSClientConfig.InsecureSkipVerify || tr.TLSClientConfig.MinVersion < 0x303 || !tr.DisableKeepAlives {
		t.Fatal("unsafe transport")
	}
	if c.CheckRedirect(nil, nil) != http.ErrUseLastResponse {
		t.Fatal("redirect allowed")
	}
}
func TestStrictJSONAndInputRejections(t *testing.T) {
	for _, raw := range []string{`{"x":1,"x":2}`, `{"x":{"a":1,"a":2}}`, `{} {}`, `{"x":NaN}`} {
		if _, e := object([]byte(raw)); e == nil {
			t.Fatal("loose JSON")
		}
	}
	v := credentials()
	v.SessionOnly = false
	if validInput(v) {
		t.Fatal("persistence mode")
	}
	v = credentials()
	v.Password = "secret\n"
	if validInput(v) {
		t.Fatal("newline")
	}
}

func TestLongPasswordNeverReducedModuloKey(t *testing.T) {
	s, _ := fixture(t)
	v := credentials()
	v.Password = strings.Repeat("x", 512)
	if s.run(context.Background(), v).AuthPosts != 0 {
		t.Fatal("oversize password submitted")
	}
}
func TestCookieBodyNotAcceptedAndMalformedIdentityStops(t *testing.T) {
	for _, cookie := range []string{"none", "short"} {
		s, f := fixture(t)
		f.cookie = cookie
		f.auth = `{"errInfo":{"no":"0"},"data":{"bduss":"SYNTHETIC_BODY_COOKIE"}}`
		r := s.run(context.Background(), credentials())
		if r.IdentityAccepted || len(f.calls) != 4 {
			t.Fatal("invalid cookie accepted")
		}
	}
	for _, body := range []string{`{"records":[{"uk":3003}]}`, `{"errno":0,"records":[{"uk":0}]}`, `{"errno":0,"records":[{"uk":3003},{"uk":3003}]}`} {
		s, f := fixture(t)
		f.identity = body
		if s.run(context.Background(), credentials()).IdentityAccepted {
			t.Fatal("invalid identity accepted")
		}
	}
}
func TestRemoteErrorCodeCannotReflectPassword(t *testing.T) {
	s, f := fixture(t)
	f.auth = `{"errInfo":{"no":"400023"}}`
	v := credentials()
	v.Password = "400023"
	r := s.run(context.Background(), v)
	if r.AuthCode != "other" {
		t.Fatal("secret echoed as code")
	}
}

type failingBody struct{}

func (failingBody) Read([]byte) (int, error) { return 0, rejected }
func TestTraceBootstrapDoesNotReadLoginPageBody(t *testing.T) {
	s, f := fixture(t)
	f.trace = "body_unread"
	if s.run(context.Background(), credentials()).Status != "session_identity_verified_no_persistence" {
		t.Fatal("unnecessary page body read")
	}
}
