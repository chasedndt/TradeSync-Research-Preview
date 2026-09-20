import type { ReactNode } from 'react'
import styles from './EvidenceTable.module.css'

export interface Column<Row> {
  id: string
  header: string
  cell: (row: Row) => ReactNode
  /** Long text wraps inside the cell instead of widening the table. */
  wrap?: boolean
}

interface EvidenceTableProps<Row> {
  label: string
  columns: readonly Column<Row>[]
  rows: readonly Row[]
  rowKey: (row: Row) => string
}

/** Stored rows as a table, newest first as state-api ordered them. Scrolls sideways rather than squeezing. */
export function EvidenceTable<Row>({ label, columns, rows, rowKey }: EvidenceTableProps<Row>) {
  return (
    <div className={styles.scroll}>
      <table className={styles.table} aria-label={label}>
        <thead>
          <tr>
            {columns.map((column) => <th key={column.id} scope="col">{column.header}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td key={column.id} className={column.wrap ? styles.wrap : undefined}>{column.cell(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
