import type { Fill, PaperPosition } from './paperTypes'
import { amount, bps, exactTime, price, usdc, words } from './paperFormat'
import styles from './PaperFills.module.css'

/** How one part was taken: the levels the book showed, and what stopped the fill there. */
const took = (fill: Fill): string => {
  const taken = fill.levels_taken
    ? `${fill.levels_taken.length} of ${fill.levels_available} displayed levels`
    : `applied to ${price(fill.reference_price)}`
  if (fill.limited_by === 'depth_bound') return `${taken}; the ${bps(fill.max_depth_bps)} depth bound stopped it there`
  if (fill.limited_by === 'displayed_levels') return `${taken}; the displayed ladder ran out`
  return taken
}

/** Every part an exit filled, each with its own price, fee and book, and the quantity still owed. */
export function PaperFills({ position: p }: { position: PaperPosition }) {
  const parts = p.exit_parts ?? []
  const owed = p.pending_exit
  if (parts.length === 0 && !owed) return null
  const remaining = p.open_quantity ?? owed?.remaining_quantity
  return (
    <section className={styles.fills} aria-label="Exit fills">
      <h5>{parts.length === 0 ? 'Exit not filled yet' : `Exit filled in ${parts.length} ${parts.length === 1 ? 'part' : 'parts'}`}</h5>
      {parts.length > 0 && (
        <div className={styles.scroll}>
          <table>
            <thead>
              <tr>
                <th scope="col">Part</th><th scope="col">Seen</th><th scope="col">Quantity</th><th scope="col">Fill</th>
                <th scope="col">Fee</th><th scope="col">Cost against the mid</th><th scope="col">Left owed</th>
              </tr>
            </thead>
            <tbody>
              {parts.map((part) => (
                <tr key={part.index}>
                  <td>{part.index}</td>
                  <td>{exactTime(part.at)}</td>
                  <td>{amount(part.quantity)}</td>
                  <td>{price(part.fill_price)}</td>
                  <td>{usdc(part.fee_usdc)}</td>
                  <td>{usdc(part.fill.cost_usdc)} · {bps(part.fill.cost_bps)} · {took(part.fill)}</td>
                  <td>{amount(part.remaining_after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {owed ? (
        <p role="status" className="tone-warn">
          {amount(remaining)} of {amount(p.quantity)} still owed on the {words(owed.rule)}: {owed.unfilled ?? 'the displayed book could not take the size'}.
          It fills at the next observation whose book can, part by part; no price is assumed for what is not filled.
        </p>
      ) : (
        parts.length > 1 && (
          <p>Exit {price(p.exit_price)} is the quantity-weighted price of the parts. Profit and loss is their sum, and each part paid its own fee.</p>
        )
      )}
    </section>
  )
}
