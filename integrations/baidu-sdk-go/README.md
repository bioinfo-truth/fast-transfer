# Official Go SDK reuse: compatibility and request codec

The module now includes a capture-only request encoder used by the Python protocol via an explicit optional encoder. See [request adapter](../../docs/sdk-request-encoder.md) for its input/output, network guard, resource costs and build instructions. It does not carry credentials or send network requests; Task upload execution and VPS deployment are still pending. The original probe documentation below remains applicable to the low-level behavior.

# Official Go SDK reuse compatibility probe

This module **imports and exercises the official SDK**, pinned to commit
`472e4a1b111eac1d6307e38802f8fe7adf7e8c21`, with Go module checksum verification.
It is a compatibility probe, not a deployed upload adapter or a Python/Go bridge.
No upstream SDK code is copied or modified. Its own license is Apache-2.0.

The selected module requires Go **1.26.2** according to its go.mod, even though
its README currently says 1.24+. Verification used the existing Go 1.27.3 toolchain.

Run with a populated module cache:

```sh
cd integrations/baidu-sdk-go
GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go test -mod=readonly -v ./...
GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go vet -mod=readonly ./...
```

Initial dependency acquisition is a separate `go mod download` using the public
module proxy and Go checksum database; `go.sum` is committed. This run acquired
only the pinned SDK (no additional SDK module dependencies), then executed tests
with a child seccomp network-denial runner and isolated HOME/cache. SDK methods
use an injected synthetic RoundTripper: no real DNS, TLS, Baidu requests or tokens.

The tests establish the adoption boundary:

- Low-level precreate / multipart slice / create encoding preserves path,
  size, uploadid, sequence and block hashes for a synthetic upload.
- An unknown create result is returned after one low-level request, no retry.
- An existing uploadid can be passed directly to SliceUpload without precreate.
  This does **not** establish server-side session lifetime or real crash recovery.
- Multipart is buffered before transport, with a fixed Content-Length. The
  source comment in upload_slice.go suggesting io.Pipe streaming is inconsistent
  with the actual client.go implementation at this pin.
- Returned slice MD5 is decoded, not checked against the submitted bytes.
  The project must verify it before recording a confirmed part.

Tests intentionally characterize behavior that affects disk/memory and recovery.
If an SDK upgrade changes it, review the project budget or checksum boundary
instead of mechanically changing expected values. A same-process scripted
transport cannot prove production TLS, remote idempotency or throughput.

See [adoption plan](../../docs/official-sdk-reuse.md) for the retained project
responsibilities and the Python-to-Go integration gap. Existing Python upload
behavior and VPS deployment are unchanged.
