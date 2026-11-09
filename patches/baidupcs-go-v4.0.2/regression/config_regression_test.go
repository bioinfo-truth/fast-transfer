// Reviewed fixed configuration paths only, under pre-init Landlock and seccomp.
package pcsconfig

import (
	"errors"
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func TestFTIdentityEntrypointsDenyBeforeParsing(t *testing.T) {
	ftConfigBoundary(t)
	c := NewConfig(filepath.Join(t.TempDir(), "never-written.json"))
	if _, err := c.SetupUserByBDUSS("", "", "", "malformed FAKE_ONLY"); err == nil || err.Error() != "verified_identity_binding_unavailable" {
		t.Fatal("identity gate failed")
	}
	if _, err := NewUserInfoByBDUSS("FAKE_ONLY"); err == nil {
		t.Fatal("BDUSS gate failed")
	}
	if _, err := NewUserInfoByInput("FAKE_ONLY", "FAKE_ONLY"); err == nil {
		t.Fatal("force gate failed")
	}
}
func TestFTAccountSaveDeniedBeforeFileCreation(t *testing.T) {
	ftConfigBoundary(t)
	p := filepath.Join(t.TempDir(), "never-written.json")
	c := NewConfig(p)
	c.BaiduUserList = BaiduUserList{&Baidu{BDUSS: "FAKE_ONLY"}}
	if err := c.Save(); err == nil || err.Error() != "verified_identity_binding_unavailable" {
		t.Fatal("persistence gate failed")
	}
	if _, err := os.Stat(p); !os.IsNotExist(err) {
		t.Fatal("credential file created")
	}
}

func ftConfigBoundary(t *testing.T) {
	t.Helper()
	expected := filepath.Join(os.Getenv("BAIDUPCS_GO_CONFIG_DIR"), ConfigName)
	if Config.configFilePath != expected || Config.configFile != nil || len(Config.BaiduUserList) != 0 {
		t.Fatal("unexpected initialized account configuration")
	}
	if _, err := os.Stat(expected); !os.IsNotExist(err) {
		t.Fatal("account configuration unexpectedly exists")
	}
	for _, path := range []string{os.Getenv("FT_OUTSIDE_CANARY"), os.Getenv("FT_CANARY_SYMLINK")} {
		if path == "" {
			t.Fatal("missing boundary probe")
		}
		if b, err := os.ReadFile(path); err == nil || b != nil || !errors.Is(err, os.ErrPermission) {
			t.Fatal("external read not denied")
		}
	}
	fd, err := syscall.Socket(syscall.AF_INET, syscall.SOCK_STREAM, 0)
	if err == nil {
		syscall.Close(fd)
		t.Fatal("socket not denied")
	}
	if !errors.Is(err, syscall.EPERM) {
		t.Fatal("unexpected socket error")
	}
}
