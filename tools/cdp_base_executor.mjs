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

// Both directions now allowlisted: USDC -> WETH and WETH -> USDC
const ALLOWED_PAIRS = [
  { from: 'USDC', to: 'WETH' },
  { from: 'WETH', to: 'USDC' },
];

function validateAllowedPair(from, to) {
  for (const p of ALLOWED_PAIRS) {
    if (p.from === from && p.to === to) return p;
  }
  throw new Error(`Allowlisted pairs are: ${ALLOWED_PAIRS.map(p => `${p.from} -> ${p.to}`).join(', ')}. Got: ${from} -> ${to}`);
}

export function validateRequest(args) {
  const pair = validateAllowedPair(args.from, args.to);
  const atomic = BigInt(Math.round(Number(args.amount) * 1_000_000));
  if (atomic <= 0n || atomic > MAX_NOTIONAL_USDC) throw new Error('Amount exceeds bounded notional cap ($100 USDC)');
  if (!Number.isInteger(args.slippageBps) || args.slippageBps < 0 || args.slippageBps > 100) throw new Error('Slippage must be 0-100 bps');
  return { ...args, amountAtomic: atomic, fromAddress: pair.from === 'USDC' ? ADDRESSES.usdc : ADDRESSES.weth, toAddress: pair.to === 'WETH' ? ADDRESSES.weth : ADDRESSES.usdc };
}

function loadSecrets() {
  const keyPath = process.env.CDP_API_KEY_FILE || `${process.env.HOME}/Documents/cdp_api_key (1).json`;
  const walletPath = process.env.CDP_WALLET_SECRET_FILE || '';
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
  const quote = await account.quoteSwap({ network: 'base', toToken: request.toAddress, fromToken: request.fromAddress, fromAmount: request.amountAtomic, slippageBps: request.slippageBps });
  if (!quote.liquidityAvailable) throw new Error('CDP reports no Base swap liquidity');
  const summary = { venue: 'coinbase_cdp_trade_api', network: 'base', from: request.amount, fromToken: request.fromAddress, toToken: request.toAddress, toAmount: quote.toAmount?.toString(), minToAmount: quote.minToAmount?.toString(), issues: quote.issues || null, execute: request.execute };
  if (!request.execute) return summary;
  const allowance = quote.issues?.allowance ?? quote.issues?.allowanceIssue;
  if (allowance && BigInt(allowance.currentAllowance ?? 0) < request.amountAtomic) {
    const client = deps.publicClient || publicClient();
    const gas = await client.getBalance({ address: ADDRESSES.wallet });
    if (gas < 1000000000000n) throw new Error('Insufficient Base ETH for Permit2 approval and swap');
    const data = encodeFunctionData({ abi: ERC20_APPROVE_ABI, functionName: 'approve', args: [ADDRESSES.permit2, request.amountAtomic] });
    const approval = await account.sendTransaction({ network: 'base', transaction: { to: ADDRESSES.usdc, data } });
    const approvalReceipt = await waitReceipt(client, approval.transactionHash);
    if (approvalReceipt.status !== 'success') throw new Error('Permit2 approval reverted');
    summary.approvalTx = approval.transactionHash;
  }
  const swap = await account.swap({ network: 'base', toToken: request.toAddress, fromToken: request.fromAddress, fromAmount: request.amountAtomic, slippageBps: request.slippageBps, idempotencyKey: `hermes-base-${request.from.toLowerCase()}-${request.to.toLowerCase()}-${Date.now()}` });
  const client = deps.publicClient || publicClient();
  const receipt = await waitReceipt(client, swap.transactionHash);
  if (receipt.status !== 'success') throw new Error('Base swap reverted');
  return { ...summary, swapTx: swap.transactionHash, status: 'finalized', blockNumber: receipt.blockNumber.toString() };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help || !args.amount) { console.log('Usage: node tools/cdp_base_executor.mjs --amount 10 [--slippage-bps 50] [--execute]'); process.exit(args.help ? 0 : 2); }
    console.log(JSON.stringify(await run(args), (_, value) => typeof value === 'bigint' ? value.toString() : value, 2));
  } catch (e) { console.error(`ERROR: ${e.message}`); process.exit(1); }
}
