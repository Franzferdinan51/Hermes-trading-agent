#!/usr/bin/env node
/** Bounded Coinbase CDP EVM Base swap executor. Default is quote-only. */
import fs from 'node:fs';
import process from 'node:process';
import { CdpClient } from '@coinbase/cdp-sdk';
import { createPublicClient, encodeFunctionData, http } from 'viem';
import { base } from 'viem/chains';

export const ADDRESSES = Object.freeze({
  wallet: '<BASE_WALLET_ADDRESS>',
  usdc: '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',
  weth: '0x4200000000000000000000000000000000000006',
  permit2: '0x000000000022d473030f116ddee9f6b43ac78ba3',
});
const MAX_NOTIONAL_USDC = 100_000_000n;
const ERC20_APPROVE_ABI = [{ type: 'function', name: 'approve', stateMutability: 'nonpayable', inputs: [{ name: 'spender', type: 'address' }, { name: 'amount', type: 'uint256' }], outputs: [{ type: 'bool' }] }];

export function parseArgs(argv) {
  const out = { from: 'USDC', to: 'WETH', amount: null, slippageBps: 50, execute: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--from') out.from = argv[++i].toUpperCase();
    else if (a === '--to') out.to = argv[++i].toUpperCase();
    else if (a === '--amount') out.amount = argv[++i];
    else if (a === '--slippage-bps') out.slippageBps = Number(argv[++i]);
    else if (a === '--execute') out.execute = true;
    else if (a === '--help') out.help = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  return out;
}

export function validateRequest(args) {
  if (args.from !== 'USDC' || args.to !== 'WETH') throw new Error('Only USDC -> WETH is allowlisted initially');
  if (!args.amount || !/^\d+(\.\d{1,6})?$/.test(args.amount)) throw new Error('Amount must be a positive USDC decimal');
  const atomic = BigInt(Math.round(Number(args.amount) * 1_000_000));
  if (atomic <= 0n || atomic > MAX_NOTIONAL_USDC) throw new Error('Amount exceeds bounded USDC notional cap');
  if (!Number.isInteger(args.slippageBps) || args.slippageBps < 0 || args.slippageBps > 100) throw new Error('Slippage must be 0-100 bps');
  return { ...args, amountAtomic: atomic };
}

function loadSecrets() {
  const keyPath = process.env.CDP_API_KEY_FILE || `${process.env.HOME}/Desktop/cdp_api_key.json`;
  const walletPath = process.env.CDP_WALLET_SECRET_FILE || `${process.env.HOME}/Documents/<PROTECTED_WALLET_SECRET_FILE>`;
  const key = JSON.parse(fs.readFileSync(keyPath, 'utf8'));
  return { apiKeyId: key.id, apiKeySecret: key.privateKey, walletSecret: fs.readFileSync(walletPath, 'utf8').trim() };
}

function publicClient() { return createPublicClient({ chain: base, transport: http(process.env.BASE_RPC_URL || 'https://mainnet.base.org') }); }

async function waitReceipt(client, hash, timeoutMs = 120000) {
  return client.waitForTransactionReceipt({ hash, timeout: timeoutMs });
}

export async function run(args, deps = {}) {
  const request = validateRequest(args);
  const cdp = deps.cdp || new CdpClient(loadSecrets());
  const account = deps.account || await cdp.evm.getAccount({ address: ADDRESSES.wallet });
  const quote = await account.quoteSwap({ network: 'base', toToken: ADDRESSES.weth, fromToken: ADDRESSES.usdc, fromAmount: request.amountAtomic, slippageBps: request.slippageBps });
  if (!quote.liquidityAvailable) throw new Error('CDP reports no Base swap liquidity');
  const summary = { venue: 'coinbase_cdp_trade_api', network: 'base', from: request.amount, fromToken: ADDRESSES.usdc, toToken: ADDRESSES.weth, toAmount: quote.toAmount?.toString(), minToAmount: quote.minToAmount?.toString(), issues: quote.issues || null, execute: request.execute };
  if (!request.execute) return summary;
  const allowance = quote.issues?.allowance ?? quote.issues?.allowanceIssue;
  if (allowance && BigInt(allowance.currentAllowance ?? 0) < request.amountAtomic) {
    const client = deps.publicClient || publicClient();
    const gas = await client.getBalance({ address: ADDRESSES.wallet });
    if (gas < 1000000000000n) throw new Error('Insufficient Base ETH for USDC Permit2 approval and swap');
    const data = encodeFunctionData({ abi: ERC20_APPROVE_ABI, functionName: 'approve', args: [ADDRESSES.permit2, request.amountAtomic] });
    const approval = await account.sendTransaction({ network: 'base', transaction: { to: ADDRESSES.usdc, data } });
    const approvalReceipt = await waitReceipt(client, approval.transactionHash);
    if (approvalReceipt.status !== 'success') throw new Error('Permit2 approval reverted');
    summary.approvalTx = approval.transactionHash;
  }
  const swap = await account.swap({ network: 'base', toToken: ADDRESSES.weth, fromToken: ADDRESSES.usdc, fromAmount: request.amountAtomic, slippageBps: request.slippageBps, idempotencyKey: `hermes-base-usdc-weth-${Date.now()}` });
  const client = deps.publicClient || publicClient();
  const receipt = await waitReceipt(client, swap.transactionHash);
  if (receipt.status !== 'success') throw new Error('Base swap reverted');
  return { ...summary, swapTx: swap.transactionHash, status: 'finalized', blockNumber: receipt.blockNumber.toString() };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help || !args.amount) { console.log('Usage: node tools/cdp_base_executor.mjs --amount 10 [--slippage-bps 50] [--execute]'); process.exit(args.help ? 0 : 2); }
    console.log(JSON.stringify(await run(args), null, 2));
  } catch (e) { console.error(`ERROR: ${e.message}`); process.exit(1); }
}
