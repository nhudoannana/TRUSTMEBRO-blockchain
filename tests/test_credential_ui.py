"""Exercise the real frontend handlers in Node; this is not a browser check."""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("wallet_exists", [True, False])
def test_credential_404_checks_wallet_before_clearing_selection(wallet_exists):
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('ui/trustmebro.html', 'utf8');
const source = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].at(-1)[1];
const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {value:'', textContent:'', hidden:true, disabled:false,
      focus(){}, scrollIntoView(){}});
    return elements.get(id);
  },
  querySelectorAll(){return [];},
};
const requests = [];
const wallet = {id:'WALLET-DEMO-EXACT-ID', name:'Demo', public_key_hex:'04abcd', address:'abcd'};
const exists = process.argv[1] === 'true';
const context = vm.createContext({document, console, fetch:async(url, options={}) => {
  requests.push({url, options});
  if (url === '/api/wallets') return {ok:true, json:async()=>[wallet]};
  if (url === '/api/credentials') return {ok:false, status:404, json:async()=>({detail:exists?'Not Found':'Ví không tồn tại.'})};
  assert.equal(url, '/api/wallets/'+wallet.id);
  return {ok:exists, status:exists?200:404, json:async()=>wallet};
}});
vm.runInContext(source.slice(0, source.indexOf('(function initTheme()')), context);
vm.runInContext('render = async () => {};', context);
(async()=>{
  const listed = await vm.runInContext('apiFetchWallets()', context);
  context.selected = listed[0];
  vm.runInContext('selectWallet(selected)', context);
  assert.equal(vm.runInContext('state.selectedWalletId', context), wallet.id);
  if (exists) {
    await vm.runInContext('handleWalletNext()', context);
    assert.equal(requests.at(-1).url, '/api/wallets/'+wallet.id);
  }
  document.getElementById('c-holder').value = 'Người học DEMO-001';
  document.getElementById('c-title').value = 'Chứng chỉ Phân tích dữ liệu';
  document.getElementById('c-date').value = '2026-10-01';
  await vm.runInContext('handleCredentialCreate({preventDefault(){}})', context);
  const post = requests.find(r=>r.url==='/api/credentials');
  assert.equal(post.options.method, 'POST');
  assert.equal(JSON.parse(post.options.body).issuer_wallet_id, wallet.id);
  assert.equal(requests.at(-1).url, '/api/wallets/'+wallet.id);
  assert.equal(vm.runInContext('state.selectedWalletId', context), exists?wallet.id:null);
  if (exists) {
    assert.match(document.getElementById('c-error').textContent, /khởi động lại backend/);
    assert.equal(vm.runInContext('state.step', context), 1);
  } else {
    assert.match(document.getElementById('w-error').textContent, /chọn lại ví/);
    assert.equal(vm.runInContext('state.step', context), 0);
  }
  assert.equal(vm.runInContext('state.signing', context), false);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", script, str(wallet_exists).lower()],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
