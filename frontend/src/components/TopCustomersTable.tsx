import type { CustomerSpend } from "../types";
import { formatCurrency } from "../utils";

interface TopCustomersTableProps {
  data: CustomerSpend[];
}

export function TopCustomersTable({ data }: TopCustomersTableProps) {
  const max = Math.max(...data.map((c) => c.revenue));

  return (
    <div className="card">
      <div className="card__head">
        <div>
          <h3 className="card__title">Top Customers</h3>
          <p className="card__sub">By lifetime spend</p>
        </div>
      </div>

      <ol className="customers">
        {data.map((customer, index) => (
          <li className="customers__row" key={customer.customer_unique_id}>
            <span className="customers__rank">{index + 1}</span>
            <span className="customers__id">{customer.customer_unique_id.slice(0, 10)}…</span>
            <span className="customers__bar" aria-hidden="true">
              <span
                className="customers__bar-fill"
                style={{ width: `${(customer.revenue / max) * 100}%` }}
              />
            </span>
            <span className="customers__value">{formatCurrency(customer.revenue)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
