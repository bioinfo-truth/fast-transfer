package codec

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"io"
	"mime/multipart"
	"net/url"
	"os"
	"strings"
	"syscall"
	"testing"
)

const target = "/apps/Xtransfer/mvp-validation/job-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/fixture.bin"

func TestControlRequestEncoding(t *testing.T) {
	for _, op := range []string{"directory", "precreate", "commit"} {
		r, e := Encode(context.Background(), Input{Operation: op, Target: target, Size: 3, Hashes: []string{"900150983cd24fb0d6963f7d28e17f72"}, UploadID: "SYNTHETIC_ONLY"})
		if e != nil {
			t.Fatal(e)
		}
		v, e := url.ParseQuery(string(r.Body))
		if e != nil {
			t.Fatal(e)
		}
		if r.Method != "POST" || r.URL != "https://pan.baidu.com/rest/2.0/xpan/file" || r.ContentType != "application/x-www-form-urlencoded" {
			t.Fatal("request shape")
		}
		if op == "directory" {
			if v.Get("rtype") != "0" || v.Get("isdir") != "1" {
				t.Fatal("directory conflict policy")
			}
		} else if v.Get("rtype") != "1" || v.Get("path") != target {
			t.Fatal("file binding")
		}
		if strings.Contains(string(r.Body), "access_token") || r.Params["access_token"] != "" {
			t.Fatal("unexpected credential")
		}
	}
}
func partInput(t *testing.T) Input {
	t.Helper()
	f, e := os.CreateTemp(t.TempDir(), "part-")
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { f.Close() })
	f.WriteString("abc")
	f.Seek(0, 0)
	fd, e := syscall.Dup(int(f.Fd()))
	if e != nil {
		t.Fatal(e)
	}
	sum := md5.Sum([]byte("abc"))
	return Input{Operation: "part", Target: target, UploadID: "SYNTHETIC_ONLY", Host: "c.pcs.baidu.com", Part: 2, PartBytes: 3, PartMD5: hex.EncodeToString(sum[:]), SourceFD: fd}
}
func TestPartUsesBoundedFDAndSDKMultipart(t *testing.T) {
	in := partInput(t)
	r, e := Encode(context.Background(), in)
	if e != nil {
		t.Fatal(e)
	}
	if r.URL != "https://c.pcs.baidu.com/rest/2.0/pcs/superfile2" || r.Params["partseq"] != "2" {
		t.Fatal("part binding")
	}
	boundary := strings.TrimPrefix(r.ContentType, "multipart/form-data; boundary=")
	p, e := multipart.NewReader(strings.NewReader(string(r.Body)), boundary).NextPart()
	if e != nil {
		t.Fatal(e)
	}
	b, e := io.ReadAll(p)
	if e != nil || string(b) != "abc" {
		t.Fatal("part bytes")
	}
}
func TestInvalidHashCannotEncodePayload(t *testing.T) {
	in := partInput(t)
	in.PartMD5 = strings.Repeat("0", 32)
	if _, e := Encode(context.Background(), in); e == nil {
		t.Fatal("wrong source accepted")
	}
}
func TestInvalidSizeCannotReadBeyondPart(t *testing.T) {
	in := partInput(t)
	in.PartBytes = 4
	if _, e := Encode(context.Background(), in); e == nil {
		t.Fatal("unbounded part accepted")
	}
}
func TestTargetsHostsAndOperationsAreRestricted(t *testing.T) {
	for _, in := range []Input{{Operation: "directory", Target: "/outside/fixture"}, {Operation: "directory", Target: target, Host: "example.org"}, {Operation: "login", Target: target}, {Operation: "commit", Target: target, Size: 3, Hashes: []string{"bad"}}} {
		if _, e := Encode(context.Background(), in); e == nil {
			t.Fatal("invalid input accepted")
		}
	}
}
func TestCancelledContextProducesNoRequest(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, e := Encode(ctx, Input{Operation: "directory", Target: target}); e == nil {
		t.Fatal("cancel ignored")
	}
}
