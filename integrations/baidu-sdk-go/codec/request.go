// Package codec reuses official SDK request encoding without credentials/network.
package codec

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"errors"
	"io"
	"net/http"
	"os"
	"regexp"
	"strings"

	"github.com/baidu-netdisk/baidu-drive-sdk-go/baidudriver/api"
)

const MaxPart = 32 * 1024 * 1024

var errCaptured = errors.New("request_captured")
var errInvalid = errors.New("sdk_codec_input_rejected")
var targetPattern = regexp.MustCompile(`^/apps/[A-Za-z][A-Za-z0-9_-]{0,63}/mvp-validation/job-[0-9a-f]{32}/[A-Za-z0-9][A-Za-z0-9._-]{0,179}$`)
var hashPattern = regexp.MustCompile(`^[0-9a-f]{32}$`)
var hostPattern = regexp.MustCompile(`^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:baidu\.com|baidupcs\.com)$`)
var idPattern = regexp.MustCompile(`^[A-Za-z0-9._=-]+$`)

type Input struct {
	Operation string   `json:"operation"`
	Target    string   `json:"target"`
	Size      int64    `json:"size"`
	Hashes    []string `json:"hashes"`
	UploadID  string   `json:"uploadid"`
	Host      string   `json:"host"`
	Part      int      `json:"part"`
	PartMD5   string   `json:"part_md5"`
	PartBytes int64    `json:"part_bytes"`
	SourceFD  int      `json:"source_fd"`
}
type Request struct {
	Method      string            `json:"method"`
	URL         string            `json:"url"`
	Params      map[string]string `json:"params"`
	Body        []byte            `json:"body"`
	ContentType string            `json:"content_type"`
}
type capture struct {
	request *Request
	calls   int
}

func (c *capture) RoundTrip(r *http.Request) (*http.Response, error) {
	c.calls++
	if c.calls != 1 {
		return nil, errInvalid
	}
	if err := r.Context().Err(); err != nil {
		return nil, err
	}
	q := r.URL.Query()
	params := make(map[string]string, len(q))
	for k, v := range q {
		if len(v) != 1 {
			return nil, errInvalid
		}
		params[k] = v[0]
	}
	if _, ok := params["access_token"]; ok {
		return nil, errInvalid
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, MaxPart+4097))
	if err != nil || len(body) > MaxPart+4096 {
		return nil, errInvalid
	}
	u := *r.URL
	u.RawQuery = ""
	c.request = &Request{r.Method, u.String(), params, body, r.Header.Get("Content-Type")}
	return nil, errCaptured
}

// Encode invokes exactly one SDK api method with a capture-only RoundTripper.
// It never sends a request or decodes a server response. Authentication remains
// in the parent application's existing transport; scene retries are not used.
func Encode(ctx context.Context, in Input) (*Request, error) {
	if !targetPattern.MatchString(in.Target) {
		return nil, errInvalid
	}
	host := in.Host
	if host == "" {
		host = "d.pcs.baidu.com"
	}
	if !hostPattern.MatchString(host) {
		return nil, errInvalid
	}
	c := &capture{}
	client := api.NewClient(api.WithHTTPClient(&http.Client{Transport: c}), api.WithPCSBaseURL("https://"+host), api.WithDebug(false))
	var err error
	switch in.Operation {
	case "directory":
		_, err = client.FileManager.Mkdir(ctx, &api.MkdirParams{Path: in.Target[:strings.LastIndex(in.Target, "/")], Rtype: api.Ptr(0)})
	case "precreate", "commit":
		if in.Size <= 0 || in.Size > 20*1000*1000*1000 || len(in.Hashes) == 0 || len(in.Hashes) > 1024 {
			return nil, errInvalid
		}
		for _, h := range in.Hashes {
			if !hashPattern.MatchString(h) {
				return nil, errInvalid
			}
		}
		if in.Operation == "precreate" {
			_, err = client.Upload.Precreate(ctx, &api.PrecreateParams{Path: in.Target, Size: in.Size, BlockList: in.Hashes, RType: api.Ptr(1)})
		} else {
			if len(in.UploadID) > 4096 || !idPattern.MatchString(in.UploadID) {
				return nil, errInvalid
			}
			_, err = client.Upload.CreateFile(ctx, &api.CreateFileParams{Path: in.Target, Size: in.Size, UploadID: in.UploadID, BlockList: in.Hashes, RType: api.Ptr(1), IsRevision: api.Ptr(0)})
		}
	case "part":
		if in.SourceFD < 3 || in.Part < 0 || in.Part >= 1024 || in.PartBytes <= 0 || in.PartBytes > MaxPart || !hashPattern.MatchString(in.PartMD5) || (len(in.UploadID) > 4096 || !idPattern.MatchString(in.UploadID)) {
			return nil, errInvalid
		}
		f := os.NewFile(uintptr(in.SourceFD), "private-bounded-part")
		if f == nil {
			return nil, errInvalid
		}
		defer f.Close()
		st, e := f.Stat()
		if e != nil || !st.Mode().IsRegular() || st.Size() != in.PartBytes {
			return nil, errInvalid
		}
		sum := md5.New()
		if _, e = io.Copy(sum, io.LimitReader(f, in.PartBytes+1)); e != nil || hex.EncodeToString(sum.Sum(nil)) != in.PartMD5 {
			return nil, errInvalid
		}
		if _, e = f.Seek(0, io.SeekStart); e != nil {
			return nil, errInvalid
		}
		_, err = client.Upload.SliceUpload(ctx, &api.SliceUploadParams{Path: in.Target, UploadID: in.UploadID, PartSeq: in.Part, File: io.LimitReader(f, in.PartBytes)})
	default:
		return nil, errInvalid
	}
	if !errors.Is(err, errCaptured) || c.calls != 1 || c.request == nil {
		return nil, errInvalid
	}
	return c.request, nil
}
