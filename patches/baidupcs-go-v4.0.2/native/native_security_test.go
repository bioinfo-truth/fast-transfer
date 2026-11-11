package requester
import("testing";"crypto/tls";"net/http";"net/http/httptest";"crypto/x509";"io")
func TestNativeSecurityTLS(t *testing.T){
 server:=httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){io.WriteString(w,"ok")}));defer server.Close()
 h:=NewHTTPClient();h.lazyInit();h.SetHTTPSecure(false)
 if h.transport.TLSClientConfig.InsecureSkipVerify||h.transport.TLSClientConfig.MinVersion<tls.VersionTLS12 {t.Fatal("TLS verification disabled")}
 if _,e:=h.Client.Get(server.URL);e==nil{t.Fatal("untrusted certificate accepted")}
 roots:=x509.NewCertPool();roots.AddCert(server.Certificate());h.transport.TLSClientConfig.RootCAs=roots
 r,e:=h.Client.Get(server.URL);if e!=nil{t.Fatal(e)};r.Body.Close()
 if _,e=h.Req("POST","http://127.0.0.1/",map[string]string{"bdusstoken":"SYNTHETIC_ONLY"},nil);e==nil{t.Fatal("plaintext credential route accepted")}
}
func TestNativeSecurityRedirect(t *testing.T){
 h:=NewHTTPClient();if h.CheckRedirect==nil||h.CheckRedirect(nil,nil)!=http.ErrUseLastResponse{t.Fatal("redirect permitted")}
}
