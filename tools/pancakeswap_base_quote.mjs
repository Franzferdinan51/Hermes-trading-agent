#!/usr/bin/env node
/** Official PancakeSwap Smart Router Base quote builder. Never signs or broadcasts. */
import { SmartRouter, SwapRouter, SMART_ROUTER_ADDRESSES } from '@pancakeswap/smart-router/evm'
import { CurrencyAmount, Percent, TradeType } from '@pancakeswap/swap-sdk-core'
import { baseTokens } from '@pancakeswap/tokens'
import { ChainId } from '@pancakeswap/chains'
import { createPublicClient, http } from 'viem'
import { base } from 'viem/chains'

const WALLET = '<BASE_WALLET_ADDRESS>'
const MAX_USDC = 100_000_000n
function args(argv) {
  const out = { amount: null, slippageBps: 50 }
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--amount') out.amount = argv[++i]
    else if (argv[i] === '--slippage-bps') out.slippageBps = Number(argv[++i])
    else if (argv[i] === '--help') out.help = true
    else throw new Error(`Unknown argument: ${argv[i]}`)
  }
  return out
}
function validate(v) {
  if (!v.amount || !/^\d+(\.\d{1,6})?$/.test(v.amount)) throw new Error('Amount must be a positive USDC decimal')
  const amount = BigInt(Math.round(Number(v.amount) * 1_000_000))
  if (amount <= 0n || amount > MAX_USDC) throw new Error('Amount exceeds $100 USDC cap')
  if (!Number.isInteger(v.slippageBps) || v.slippageBps < 0 || v.slippageBps > 100) throw new Error('Slippage must be 0-100 bps')
  return { ...v, amount }
}
async function quote(input) {
  const client = createPublicClient({ chain: base, transport: http(process.env.BASE_RPC_URL || 'https://mainnet.base.org') })
  const onChainProvider = () => client
  const quoteProvider = SmartRouter.createQuoteProvider({ onChainProvider })
  const [v2, v3] = await Promise.all([
    SmartRouter.getV2CandidatePools({ onChainProvider, currencyA: baseTokens.usdc, currencyB: baseTokens.weth }),
    SmartRouter.getV3CandidatePools({ onChainProvider, subgraphProvider: () => null, currencyA: baseTokens.usdc, currencyB: baseTokens.weth }),
  ])
  const trade = await SmartRouter.getBestTrade(
    CurrencyAmount.fromRawAmount(baseTokens.usdc, input.amount), baseTokens.weth, TradeType.EXACT_INPUT,
    { gasPriceWei: () => client.getGasPrice(), poolProvider: SmartRouter.createStaticPoolProvider([...v2, ...v3]), quoteProvider, maxHops: 3, maxSplits: 4 },
  )
  if (!trade) throw new Error('No PancakeSwap route found')
  const { value, calldata } = SwapRouter.swapCallParameters(trade, { recipient: WALLET, slippageTolerance: new Percent(input.slippageBps, 10_000) })
  return { venue: 'pancakeswap_smart_router', chain: 'base', router: SMART_ROUTER_ADDRESSES[ChainId.BASE], from: 'USDC', to: 'WETH', amount: input.amount.toString(), expectedOutput: trade.outputAmount.quotient.toString(), slippageBps: input.slippageBps, candidatePools: { v2: v2.length, v3: v3.length }, calldata, value, execute: false, note: 'Quote-only. No Permit2 approval, signing, or broadcast occurs.' }
}
const raw = args(process.argv.slice(2))
if (raw.help || !raw.amount) console.log('Usage: node tools/pancakeswap_base_quote.mjs --amount 1 [--slippage-bps 50]')
else quote(validate(raw)).then(x => console.log(JSON.stringify(x, null, 2))).catch(e => { console.error(`ERROR: ${e.message}`); process.exit(1) })
