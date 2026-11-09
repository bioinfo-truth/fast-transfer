"""Offline applicability/static checks. Never builds or executes upstream code."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def verify(source):
    here = Path(__file__).resolve().parent
    baseline = json.loads((here / 'baseline.json').read_text())
    patch = here / 'security-candidate.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == baseline['patch_sha256']
    with tempfile.TemporaryDirectory(prefix='ft-pcs-patch-check-') as folder:
        work = Path(folder)
        for name, expected in baseline['original_sha256'].items():
            data = (source / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == expected, name
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        subprocess.run(['git', 'apply', '--check', '--unidiff-zero', str(patch)], cwd=work, check=True)
        subprocess.run(['git', 'apply', '--unidiff-zero', str(patch)], cwd=work, check=True)
        client = (work / 'requester/http_client.go').read_text()
        assert 'InsecureSkipVerify: true' not in client
        assert 'CheckRedirect: denyRedirect' in client
        assert 'h.Client.Transport = guardedTransport{next: h.transport}' in client
        assert client.index('h.lazyInit()') < client.index('return h')
        assert 'InsecureSkipVerify: !h.https' not in (work / 'requester/dial.go').read_text()
        policy = (work / 'requester/security_policy.go').read_text()
        assert policy.index('u.Scheme != "https"') < policy.index('g.next.RoundTrip(req)')
        assert 'url.ParseQuery(u.RawQuery)' in policy
        assert 'config.InsecureSkipVerify' in policy
        assert 'return ErrRequestPolicy // No Location' in policy
        setup = (work / 'internal/pcsconfig/maniper.go').read_text()
        start = setup.index('func (c *PCSConfig) SetupUserByBDUSS')
        assert setup.index('RequireVerifiedIdentityBinding()', start) < setup.index('regexp.Compile', start)
        gate = (work / 'internal/pcsconfig/identity_gate.go').read_text()
        assert 'return errors.New("verified_identity_binding_unavailable")' in gate
        assert 'return nil' not in gate
        config = (work / 'internal/pcsconfig/pcsconfig.go').read_text()
        start = config.index('func (c *PCSConfig) Save()')
        assert config.index('len(c.BaiduUserList)', start) < config.index('c.lazyOpenConfigFile()', start)
        login = (work / 'main.go').read_text()
        assert login.index('RequireVerifiedIdentityBinding()') < login.index('var bduss, ptoken, stoken, cookies string')
    return {'baseline_hashes': 'passed', 'patch_applicability': 'passed',
            'audited_static_constraints': 'passed',
            'go_compilation': 'not_run_no_toolchain', 'go_tests': 'not_run_no_toolchain',
            'upstream_client_executed': False, 'account_requests': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    print(json.dumps(verify(parser.parse_args().source), indent=2))
