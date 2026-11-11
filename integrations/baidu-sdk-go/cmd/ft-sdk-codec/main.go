// ft-sdk-codec is a request encoder, not a network uploader or credential tool.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"github.com/bioinfo-truth/fast-transfer/integrations/baidu-sdk-go/codec"
	"io"
	"os"
	"syscall"
	"time"
)

func run() int {
	if syscall.Setrlimit(syscall.RLIMIT_CORE, &syscall.Rlimit{Cur: 0, Max: 0}) != nil {
		return 2
	}
	raw, e := io.ReadAll(io.LimitReader(os.Stdin, 65537))
	if e != nil || len(raw) > 65536 {
		return 2
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	var in codec.Input
	if d.Decode(&in) != nil {
		return 2
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return 2
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	req, err := codec.Encode(ctx, in)
	if err != nil {
		return 2
	}
	if json.NewEncoder(os.Stdout).Encode(req) != nil {
		return 2
	}
	return 0
}
func main() { os.Exit(run()) }
