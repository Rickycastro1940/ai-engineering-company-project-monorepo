'use client';

import React, { useEffect, useState } from 'react';
import { inventoryApi, InventoryOrder } from '../../../../../../lib/inventory';

const TOKEN_KEYS = ['token', 'access_token', 'authToken'];
const LOGIN_PATH = '/login';

const getCookieValue = (name: string): string | null => {
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
};

const getStoredToken = (): string | null => {
  for (const key of TOKEN_KEYS) {
    const token = localStorage.getItem(key);
    if (token) {
      return token;
    }
  }

  for (const key of TOKEN_KEYS) {
    const token = getCookieValue(key);
    if (token) {
      return token;
    }
  }

  return null;
};

const formatDate = (value: string): string => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value || '-' : parsed.toLocaleString();
};

type OutboundOrderRow = {
  orderId: string;
  productName: string;
  quantity: number;
  createdAt: string;
  userUuid: string;
};

export default function InventoryOutboundOrderPage() {
  const [orders, setOrders] = useState<InventoryOrder[]>([]);
  const [isAuthorizing, setIsAuthorizing] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  const rows: OutboundOrderRow[] = orders
    .filter((order) => order.type === 'OUTBOUND')
    .flatMap((order) => {
      if (order.items.length === 0) {
        return [
          {
            orderId: order.id,
            productName: '-',
            quantity: 0,
            createdAt: order.created_at,
            userUuid: order.created_by || '-',
          },
        ];
      }

      return order.items.map((item) => ({
        orderId: order.id,
        productName: item.name || `Product ${item.product_id}`,
        quantity: item.quantity,
        createdAt: order.created_at,
        userUuid: order.created_by || '-',
      }));
    });

  const loadOutboundOrders = async () => {
    setIsLoading(true);
    setError('');

    try {
      const response = await inventoryApi.getOrdersHistory();
      setOrders(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load Outbound Order records';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      window.location.replace(LOGIN_PATH);
      return;
    }

    setIsAuthorizing(false);
    void loadOutboundOrders();
  }, []);

  return (
    <main style={{ maxWidth: '640px', padding: '24px' }}>
      {isAuthorizing && <p>Redirecting to login...</p>}

      {!isAuthorizing && (
        <>
          <h1>Outbound Order List</h1>
          <p>Read-only list of Outbound Order records.</p>

          <a
            href="/backoffice/inventory/orders/outbound/create"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              marginTop: '12px',
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #98a2b3',
              background: '#f8f9fc',
              color: '#344054',
              textDecoration: 'none',
            }}
          >
            Create Outbound Order
          </a>

          {error && (
            <div
              role="alert"
              aria-live="assertive"
              style={{
                marginTop: '12px',
                color: '#b42318',
                background: '#fee4e2',
                border: '1px solid #fda29b',
                borderRadius: '8px',
                padding: '10px 12px',
                fontWeight: 600,
              }}
            >
              {error}
            </div>
          )}

          <button type="button" onClick={() => void loadOutboundOrders()} disabled={isLoading} style={{ marginTop: '12px' }}>
            {isLoading ? 'Loading...' : 'Refresh Outbound Order List'}
          </button>

          {!isLoading && !error && rows.length === 0 && (
            <p style={{ marginTop: '12px' }}>No Outbound Order records found.</p>
          )}

          {!isLoading && !error && rows.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '16px' }}>
              <thead>
                <tr>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>name</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>quantity</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>created_at</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>created_by</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.orderId}-${row.productName}-${index}`}>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{row.productName}</td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{row.quantity}</td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{formatDate(row.createdAt)}</td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{row.userUuid}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </main>
  );
}
