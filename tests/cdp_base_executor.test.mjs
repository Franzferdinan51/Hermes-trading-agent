import test from 'node:test';
import assert from 'node:assert/strict';
import { parseArgs, validateRequest, run, ADDRESSES } from '../tools/cdp_base_executor.mjs';

test('defaults to dry-run USDC to WETH', () => {
  const x = parseArgs(['--amount','10']);
  assert.equal(x.from, 'USDC'); assert.equal(x.to, 'WETH'); assert.equal(x.execute, false);
});

test('rejects non-allowlisted pairs', () => {
  assert.throws(() => validateRequest({from:'USDC',to:'ETH',amount:'10',slippageBps:50}), /allowlisted/);
});

test('rejects excessive slippage and notional', () => {
  assert.throws(() => validateRequest({from:'USDC',to:'WETH',amount:'10',slippageBps:101}), /Slippage/);
  assert.throws(() => validateRequest({from:'USDC',to:'WETH',amount:'101',slippageBps:50}), /bounded/);
});

test('dry-run returns quote and never sends', async () => {
  let sent = false;
  const account = {
    quoteSwap: async (o) => ({ liquidityAvailable:true, toAmount:5490000000000000n, minToAmount:5460000000000000n, issues:{allowance:{currentAllowance:'0',spender:ADDRESSES.permit2}} }),
    sendTransaction: async () => { sent=true; throw new Error('must not send'); },
  };
  const result = await run({from:'USDC',to:'WETH',amount:'10',slippageBps:50,execute:false}, {account});
  assert.equal(result.venue, 'coinbase_cdp_trade_api'); assert.equal(result.toAmount, '5490000000000000'); assert.equal(sent, false);
});
