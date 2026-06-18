"use client";

import { useEffect, useState } from "react";
import ProtectedRoute from "../components/ProtectedRoute";
import { apiRequest } from "../lib/api";

export default function DashboardPage() {
  const [inventory, setInventory] = useState([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiRequest("/inventory")
      .then(setInventory)
      .catch((requestError) => setError(requestError.message))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <ProtectedRoute>
      <main className="page-shell">
        <section className="hero">
          <p className="eyebrow">Protected view</p>
          <h1>Operations dashboard</h1>
          <p>Authenticated users can see protected inventory data from the API.</p>
        </section>

        <section className="card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Protected API call</p>
              <h2>Inventory</h2>
            </div>
            <span className="badge">Bearer token required</span>
          </div>

          {isLoading ? <p>Loading inventory...</p> : null}
          {error ? <p className="error">{error}</p> : null}
          {!isLoading && !error ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Quantity</th>
                    <th>Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.map((product) => (
                    <tr key={product.product_id}>
                      <td>{product.name}</td>
                      <td>{product.quantity}</td>
                      <td>{product.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      </main>
    </ProtectedRoute>
  );
}
