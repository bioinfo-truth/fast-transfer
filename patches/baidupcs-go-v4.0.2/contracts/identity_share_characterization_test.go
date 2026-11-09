// Characterization of fixed source gaps, NOT proof of authentication or sharing.
package baidupcs

import (
	"io"
	"net/http"
	"strings"
	"testing"
)

type ftContractTransport struct {
	body    string
	calls   int
	inspect func(*http.Request)
}

func (f *ftContractTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	f.calls++
	if f.inspect != nil {
		f.inspect(r)
	}
	return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(f.body)), Request: r}, nil
}
func ftContractClient(body string) (*BaiduPCS, *ftContractTransport) {
	p := NewPCS(0, "FAKE_ONLY")
	p.SetHTTPS(true)
	f := &ftContractTransport{body: body}
	p.GetClient().Client.Transport = f
	return p, f
}
func TestFTCharacterizeUKResponse(t *testing.T) {
	for _, c := range []struct {
		name, body string
		want       int64
		err        bool
	}{
		{"valid_fixture", `{"errno":0,"records":[{"uk":101}]}`, 101, false},
		{"missing_errno_is_accepted_gap", `{"records":[{"uk":101}]}`, 101, false},
		{"zero_uk_is_accepted_gap", `{"errno":0,"records":[{"uk":0}]}`, 0, false},
		{"negative_uk_is_accepted_gap", `{"errno":0,"records":[{"uk":-1}]}`, -1, false},
		{"expired_rejected", `{"errno":-6,"records":[]}`, 0, true},
		{"two_records_rejected", `{"errno":0,"records":[{"uk":101},{"uk":102}]}`, 0, true},
		{"string_type_rejected", `{"errno":0,"records":[{"uk":"101"}]}`, 0, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			p, f := ftContractClient(c.body)
			f.inspect = func(r *http.Request) {
				if r.Method != "GET" || r.URL.Scheme != "https" || r.URL.Path != "/api/user/getinfo" || r.URL.Query().Get("need_selfinfo") != "1" {
					t.Fatal("identity request drift")
				}
			}
			uk, e := p.UK()
			if (e != nil) != c.err || uk != c.want || f.calls != 1 {
				t.Fatal("unexpected fixed-source characterization")
			}
		})
	}
}
func TestFTCharacterizeShareResponse(t *testing.T) {
	for _, c := range []struct {
		name, body string
		err        bool
	}{
		{"fixture_success", `{"errno":0,"link":"https://pan.baidu.com/s/FAKE_ONLY","shareid":7}`, false},
		{"missing_errno_id_accepted_gap", `{"link":"https://pan.baidu.com/s/FAKE_ONLY"}`, false},
		{"unsafe_link_accepted_gap", `{"errno":0,"link":"javascript:FAKE_ONLY","shareid":7}`, false},
		{"empty_link_rejected", `{"errno":0,"shareid":7}`, true},
		{"business_denial_rejected", `{"errno":-1}`, true},
	} {
		t.Run(c.name, func(t *testing.T) {
			p, f := ftContractClient(c.body)
			f.inspect = func(r *http.Request) {
				if r.Method != "POST" || r.URL.Scheme != "https" || r.URL.Path != "/share/pset" {
					t.Fatal("share request drift")
				}
				if err := r.ParseForm(); err != nil {
					t.Fatal("fixture form parse")
				}
				if r.Form.Get("period") != "7" || r.Form.Get("pwd") != "f1a2" || r.Form.Get("schannel") != "4" || !strings.Contains(r.Form.Get("path_list"), "/apps/Xtransfer/offline-fixture/synthetic.fna.gz") {
					t.Fatal("share scope fields drift")
				}
			}
			result, e := p.ShareSet([]string{"/apps/Xtransfer/offline-fixture/synthetic.fna.gz"}, &ShareOption{Password: "f1a2", Period: 7})
			if (e != nil) != c.err || f.calls != 1 {
				t.Fatal("unexpected fixed-source characterization")
			}
			if e == nil && result.Pwd != "f1a2" {
				t.Fatal("source no longer copies requested pwd")
			}
		})
	}
}
