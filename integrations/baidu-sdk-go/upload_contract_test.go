// Package sdkreuse characterizes the pinned official SDK before runtime adoption.
// All credentials, paths, upload IDs and responses below are synthetic.
package sdkreuse

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/baidu-netdisk/baidu-drive-sdk-go/baidudriver/api"
)

type scriptedTransport struct {
	calls  int
	handle func(*http.Request) (*http.Response, error)
}

func (s *scriptedTransport) RoundTrip(r *http.Request) (*http.Response, error) {
	s.calls++
	return s.handle(r)
}
func reply(body string) *http.Response {
	return &http.Response{StatusCode: 200, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body))}
}
func client(s *scriptedTransport) *api.Client {
	return api.NewClient(api.WithHTTPClient(&http.Client{Transport: s, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}), api.WithAccessToken("SYNTHETIC_TOKEN_ONLY"), api.WithDebug(false))
}

const target = "/apps/Xtransfer/mvp-validation/synthetic-sdk-only/test.bin"
const partMD5 = "900150983cd24fb0d6963f7d28e17f72"

func TestSDKLowLevelThreeStepContract(t *testing.T) {
	s := &scriptedTransport{}
	s.handle = func(r *http.Request) (*http.Response, error) {
		if r.URL.Scheme != "https" || r.URL.Query().Get("access_token") != "SYNTHETIC_TOKEN_ONLY" {
			t.Fatal("unexpected transport/auth shape")
		}
		switch s.calls {
		case 1:
			if r.URL.Host != "pan.baidu.com" || r.URL.Query().Get("method") != "precreate" {
				t.Fatal("precreate route")
			}
			if e := r.ParseForm(); e != nil {
				t.Fatal(e)
			}
			if r.PostForm.Get("path") != target || r.PostForm.Get("size") != "3" || r.PostForm.Get("block_list") != `["`+partMD5+`"]` {
				t.Fatal("precreate binding")
			}
			return reply(`{"errno":0,"uploadid":"SYNTHETIC_UPLOAD_ONLY","return_type":1,"block_list":[0]}`), nil
		case 2:
			if r.URL.Host != "d.pcs.baidu.com" || r.URL.Path != "/rest/2.0/pcs/superfile2" || r.URL.Query().Get("path") != target || r.URL.Query().Get("partseq") != "0" || r.URL.Query().Get("uploadid") != "SYNTHETIC_UPLOAD_ONLY" {
				t.Fatal("slice binding")
			}
			if r.ContentLength <= 3 {
				t.Fatal("missing fixed multipart length")
			}
			mr, e := r.MultipartReader()
			if e != nil {
				t.Fatal(e)
			}
			p, e := mr.NextPart()
			if e != nil {
				t.Fatal(e)
			}
			b, e := io.ReadAll(p)
			if e != nil || string(b) != "abc" || p.FormName() != "file" {
				t.Fatal("multipart bytes")
			}
			return reply(`{"md5":"` + partMD5 + `"}`), nil
		case 3:
			r.ParseForm()
			if r.URL.Query().Get("method") != "create" || r.PostForm.Get("uploadid") != "SYNTHETIC_UPLOAD_ONLY" || r.PostForm.Get("block_list") != `["`+partMD5+`"]` || r.PostForm.Get("path") != target {
				t.Fatal("commit binding")
			}
			return reply(`{"errno":0,"fs_id":123,"path":"` + target + `","size":3,"md5":"` + partMD5 + `"}`), nil
		default:
			t.Fatal("unexpected replay")
			return nil, errors.New("unexpected replay")
		}
	}
	c := client(s)
	ctx := context.Background()
	pre, e := c.Upload.Precreate(ctx, &api.PrecreateParams{Path: target, Size: 3, BlockList: []string{partMD5}})
	if e != nil {
		t.Fatal(e)
	}
	part, e := c.Upload.SliceUpload(ctx, &api.SliceUploadParams{Path: target, UploadID: pre.UploadID, PartSeq: 0, File: strings.NewReader("abc")})
	if e != nil {
		t.Fatal(e)
	}
	created, e := c.Upload.CreateFile(ctx, &api.CreateFileParams{Path: target, UploadID: pre.UploadID, Size: 3, BlockList: []string{part.MD5}})
	if e != nil || created.FsID != 123 || created.Size != 3 || created.Path != target || s.calls != 3 {
		t.Fatal("three step result")
	}
}
func TestSDKLowLevelDoesNotReplayUnknownCommit(t *testing.T) {
	s := &scriptedTransport{handle: func(*http.Request) (*http.Response, error) { return nil, errors.New("SYNTHETIC_DROPPED_REPLY") }}
	_, e := client(s).Upload.CreateFile(context.Background(), &api.CreateFileParams{Path: target, Size: 3, UploadID: "SYNTHETIC_UPLOAD_ONLY", BlockList: []string{partMD5}})
	if e == nil || s.calls != 1 {
		t.Fatal("commit was replayed or error lost")
	}
}
func TestSDKPartIsBufferedBeforeTransport(t *testing.T) {
	reader := bytes.NewBufferString("abc")
	s := &scriptedTransport{handle: func(r *http.Request) (*http.Response, error) {
		if reader.Len() != 0 || r.ContentLength <= 3 {
			t.Fatal("multipart buffering behavior changed; review budget")
		}
		return reply(`{"md5":"` + partMD5 + `"}`), nil
	}}
	_, e := client(s).Upload.SliceUpload(context.Background(), &api.SliceUploadParams{Path: target, UploadID: "SYNTHETIC_UPLOAD_ONLY", File: reader})
	if e != nil {
		t.Fatal(e)
	}
}
func TestSDKChecksumValidationRemainsCallerResponsibility(t *testing.T) {
	s := &scriptedTransport{handle: func(*http.Request) (*http.Response, error) {
		return reply(`{"md5":"00000000000000000000000000000000"}`), nil
	}}
	p, e := client(s).Upload.SliceUpload(context.Background(), &api.SliceUploadParams{Path: target, UploadID: "SYNTHETIC_UPLOAD_ONLY", File: strings.NewReader("abc")})
	if e != nil || p.MD5 == partMD5 {
		t.Fatal("SDK behavior changed; review project checksum boundary")
	}
}
func TestSDKReusesRecoveredUploadIDWithoutPrecreate(t *testing.T) {
	s := &scriptedTransport{handle: func(r *http.Request) (*http.Response, error) {
		if r.URL.Query().Get("uploadid") != "SYNTHETIC_RECOVERED_ONLY" || r.URL.Query().Get("partseq") != "2" {
			t.Fatal("recovered session lost")
		}
		return reply(`{"md5":"` + partMD5 + `"}`), nil
	}}
	_, e := client(s).Upload.SliceUpload(context.Background(), &api.SliceUploadParams{Path: target, UploadID: "SYNTHETIC_RECOVERED_ONLY", PartSeq: 2, File: strings.NewReader("abc")})
	if e != nil || s.calls != 1 {
		t.Fatal("unexpected recovery orchestration")
	}
}
