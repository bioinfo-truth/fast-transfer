package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func certificate(t *testing.T, names []string) (tls.Certificate, *x509.Certificate) {
	pub, key, e := ed25519.GenerateKey(rand.Reader)
	if e != nil {
		t.Fatal(e)
	}
	cert := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "Synthetic local TLS only"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), DNSNames: names, KeyUsage: x509.KeyUsageDigitalSignature | x509.KeyUsageCertSign, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, BasicConstraintsValid: true, IsCA: true}
	der, e := x509.CreateCertificate(rand.Reader, cert, cert, pub, key)
	if e != nil {
		t.Fatal(e)
	}
	encoded, e := x509.MarshalPKCS8PrivateKey(key)
	if e != nil {
		t.Fatal(e)
	}
	pair, e := tls.X509KeyPair(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: encoded}))
	if e != nil {
		t.Fatal(e)
	}
	parsed, e := x509.ParseCertificate(der)
	if e != nil {
		t.Fatal(e)
	}
	return pair, parsed
}
func localClient(t *testing.T, names []string, trust bool, handler http.Handler) (*session, *httptest.Server) {
	pair, cert := certificate(t, names)
	server := httptest.NewUnstartedServer(handler)
	server.TLS = &tls.Config{Certificates: []tls.Certificate{pair}, MinVersion: tls.VersionTLS12}
	server.StartTLS()
	t.Cleanup(server.Close)
	c, tr := productionClient()
	if trust {
		tr.TLSClientConfig.RootCAs = x509.NewCertPool()
		tr.TLSClientConfig.RootCAs.AddCert(cert)
	}
	tr.DialContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		if address != "wappass.baidu.com:443" && address != "pan.baidu.com:443" {
			t.Fatal("wrong intended host")
		}
		return (&net.Dialer{}).DialContext(ctx, "tcp", server.Listener.Addr().String())
	}
	t.Cleanup(tr.CloseIdleConnections)
	return &session{client: c}, server
}
func TestLocalTLSValidCertificateAndFixedHost(t *testing.T) {
	s, _ := localClient(t, []string{"wappass.baidu.com"}, true, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, `{"ok":true}`) }))
	if _, e := s.request(context.Background(), "bootstrap_time", "GET", "https://wappass.baidu.com/wp/api/security/antireplaytoken", nil, ""); e != nil {
		t.Fatal("local TLS failed")
	}
}
func TestLocalTLSWrongHostnameAndUntrustedChainNeverReachHTTP(t *testing.T) {
	for _, v := range []struct {
		names []string
		trust bool
	}{{[]string{"other.invalid"}, true}, {[]string{"wappass.baidu.com"}, false}} {
		var hits atomic.Int32
		s, _ := localClient(t, v.names, v.trust, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { hits.Add(1) }))
		if _, e := s.request(context.Background(), "bootstrap_time", "GET", "https://wappass.baidu.com/wp/api/security/antireplaytoken", nil, ""); e == nil || hits.Load() != 0 {
			t.Fatal("unsafe TLS accepted")
		}
	}
}
func TestLocalTLSDroppedPostReplyIsUnknownAndNeverRepeated(t *testing.T) {
	f := &fakeRT{t: t}
	var posts atomic.Int32
	s, _ := localClient(t, []string{"wappass.baidu.com", "pan.baidu.com"}, true, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/wp/api/login" {
			posts.Add(1)
			io.Copy(io.Discard, r.Body)
			c, _, e := w.(http.Hijacker).Hijack()
			if e == nil {
				c.Close()
			}
			return
		}
		clone := r.Clone(r.Context())
		clone.URL.Scheme = "https"
		clone.URL.Host = r.Host
		response, e := f.RoundTrip(clone)
		if e != nil {
			t.Error(e)
			return
		}
		for k, values := range response.Header {
			for _, v := range values {
				w.Header().Add(k, v)
			}
		}
		w.WriteHeader(response.StatusCode)
		io.Copy(w, response.Body)
	}))
	r := s.run(context.Background(), credentials())
	if r.Status != "authentication_outcome_unknown" || r.AuthPosts != 1 || posts.Load() != 1 {
		t.Fatal("post replay or incorrect outcome")
	}
}
func TestLocalTLSRedirectIsNotFollowed(t *testing.T) {
	var hits atomic.Int32
	s, _ := localClient(t, []string{"wappass.baidu.com"}, true, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.Header().Set("Location", "https://other.invalid/")
		w.WriteHeader(302)
		io.WriteString(w, strings.Repeat("SYNTHETIC_ONLY", 2))
	}))
	if _, e := s.request(context.Background(), "bootstrap_time", "GET", "https://wappass.baidu.com/wp/api/security/antireplaytoken", nil, ""); e == nil || hits.Load() != 1 {
		t.Fatal("redirect followed")
	}
}
