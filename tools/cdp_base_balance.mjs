#!/usr/bin/env node
/** Read-only Coinbase CDP Base wallet balance probe. */
import fs from 'node:fs';
import { CdpClient } from '@coinbase/cdp-sdk';

const WALLET = '<BASE_WALLET_ADDRESS>';
const keyPath = process.env.CDP_API_KEY_FILE || `${process.env.HOME}/Documents/cdp_api_key (1).json`;
const walletPath = process.env.CDP_WALLET_SECRET_FILE || `${process.env.HOME}/Documents/<PROTECTED_WALLET_SECRET_FILE>`;

const key = JSON.parse(fs.readFileSync(keyPath, 'utf8'));
const cdp = new CdpClient({
  apiKeyId: key.id,
  apiKeySecret: key.privateKey,
  walletSecret: fs.readFileSync(walletPath, 'utf8').trim(),
});
const account = await cdp.evm.getAccount({ address: WALLET });
const result = await account.listTokenBalances({ network: 'base', pageSize: 100 });
const balances = result.balances.map((entry) => ({
  symbol: entry.token.symbol,
  name: entry.token.name,
  contract: entry.token.contractAddress,
  amount: entry.amount.amount.toString(),
  decimals: entry.amount.decimals,
}));
console.log(JSON.stringify({
  source: 'coinbase_cdp_sdk',
  network: 'base',
  wallet: WALLET,
  balances,
  verified: true,
}, null, 2));
