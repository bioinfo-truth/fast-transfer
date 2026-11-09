// Compile-only this round: full configuration dependency initialization not cleared for execution.
package pcsconfig

import (
	"os"
	"path/filepath"
	"testing"
)

func TestFTIdentityEntrypointsDenyBeforeParsing(t *testing.T) {
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
