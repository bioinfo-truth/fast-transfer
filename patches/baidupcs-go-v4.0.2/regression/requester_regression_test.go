package requester

import (
	"crypto/tls"
	"errors"
	"io"
	"net/http"
	"os"
	"strings"
	"syscall"
	"testing"
)

type ftTransport struct {
	calls    int
	response *http.Response
	err      error
}

func (f *ftTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	f.calls++
	if f.err != nil {
		return nil, f.err
	}
	if f.response != nil {
		f.response.Request = r
		return f.response, nil
	}
	return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader("FAKE_ONLY")), Request: r}, nil
}
func ftClient() (*HTTPClient, *ftTransport) {
	h := NewHTTPClient()
	f := &ftTransport{}
	h.Client.Transport = guardedTransport{next: f}
	return h, f
}
func TestFTActualClientTLSAndSwitch(t *testing.T) {
	h := NewHTTPClient()
	if _, ok := h.Client.Transport.(guardedTransport); !ok {
		t.Fatal("default transport not guarded")
	}
	for _, enabled := range []bool{false, true} {
		h.SetHTTPSecure(enabled)
		cfg := h.transport.TLSClientConfig
		if cfg.InsecureSkipVerify || cfg.MinVersion < tls.VersionTLS12 {
			t.Fatal("TLS weakened")
		}
	}
	if h.Client.CheckRedirect == nil {
		t.Fatal("redirect hook absent")
	}
}
func TestFTActualReqRejectsHTTPBeforeTransport(t *testing.T) {
	h, f := ftClient()
	if _, err := h.Req("POST", "http://pan.baidu.com/offline-fixture", map[string]string{"BDUSS": "FAKE_ONLY"}, nil); err != ErrRequestFailed {
		t.Fatal("unsafe request accepted")
	}
	if f.calls != 0 {
		t.Fatal("HTTP reached transport")
	}
}
func TestFTActualReqConstructionAndTransportErrors(t *testing.T) {
	h, f := ftClient()
	for _, input := range [][2]string{{"BAD\nFAKE_ONLY", "https://pan.baidu.com/fixture"}, {"GET", "https://pan.baidu.com/%zzFAKE_ONLY"}} {
		if _, err := h.Req(input[0], input[1], nil, nil); err != ErrRequestPolicy {
			t.Fatal("construction error escaped")
		}
	}
	if f.calls != 0 {
		t.Fatal("malformed request reached transport")
	}
	f.err = errors.New("FAKE_ONLY sensitive error")
	if _, err := h.Req("GET", "https://pan.baidu.com/fixture", nil, nil); err != ErrRequestFailed {
		t.Fatal("transport error escaped")
	}
}
func TestFTActualClientRedirectIsStopped(t *testing.T) {
	h, f := ftClient()
	f.response = &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"https://other.baidu.com/offline-fixture"}}, Body: io.NopCloser(strings.NewReader(""))}
	if _, err := h.Req("GET", "https://pan.baidu.com/fixture", nil, map[string]string{"Cookie": "BDUSS=FAKE_ONLY"}); err != ErrRequestFailed {
		t.Fatal("redirect accepted")
	}
	if f.calls != 1 {
		t.Fatal("redirect was followed")
	}
}

type ftReadError struct{}

func (ftReadError) Read(p []byte) (int, error) {
	copy(p, "X")
	return 1, errors.New("FAKE_ONLY read error")
}
func TestFTActualFetchAndHTTPGetReadFailure(t *testing.T) {
	h, f := ftClient()
	f.response = &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(ftReadError{})}
	if data, err := h.Fetch("GET", "https://pan.baidu.com/fixture", nil, nil); data != nil || err != ErrRequestFailed {
		t.Fatal("Fetch leaked partial data/error")
	}
	saved := DefaultClient
	DefaultClient = h
	defer func() { DefaultClient = saved }()
	f.response = &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(ftReadError{})}
	if data, err := HTTPGet("https://pan.baidu.com/fixture"); data != nil || err != ErrRequestFailed {
		t.Fatal("HTTPGet bypassed protected path")
	}
}
func TestFTActualReqSuccessUsesOnlyMemory(t *testing.T) {
	h, f := ftClient()
	body, err := h.Fetch("GET", "https://pan.baidu.com/offline-fixture", nil, nil)
	if err != nil || string(body) != "FAKE_ONLY" || f.calls != 1 {
		t.Fatal("fake transport flow failed")
	}
}
func TestFTRuntimeBoundary(t *testing.T) {
	for _, path := range []string{os.Getenv("FT_OUTSIDE_CANARY"), os.Getenv("FT_CANARY_SYMLINK")} {
		if path == "" {
			t.Fatal("missing boundary probe")
		}
		if data, err := os.ReadFile(path); err == nil || data != nil || !errors.Is(err, os.ErrPermission) {
			t.Fatal("external read not denied")
		}
	}
	fd, err := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, 0)
	if err == nil {
		syscall.Close(fd)
		t.Fatal("network not denied")
	}
	if !errors.Is(err, syscall.EPERM) {
		t.Fatal("unexpected socket error")
	}
}
