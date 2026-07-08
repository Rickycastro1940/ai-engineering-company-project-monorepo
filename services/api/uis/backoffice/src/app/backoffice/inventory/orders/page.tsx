'use client';

import React, { useEffect, useState } from 'react';
import { inventoryApi, InventoryOrder } from '../../../../../lib/inventory';

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

const getOrderTypePresentation = (orderType: 'INBOUND' | 'OUTBOUND') => {
  if (orderType === 'INBOUND') {
    return {
      label: 'Inbound',
      icon: '+',
      color: '#067647',
      background: '#ecfdf3',
      border: '#abefc6',
      rowAccent: '#f6fef9',
    };
  }

  return {
    label: 'Outbound',
    icon: '-',
    color: '#b42318',
    background: '#fee4e2',
    border: '#fda29b',
    rowAccent: '#fff7f7',
  };
};

type OrderRow = {
  orderId: string;
  productName: string;
  quantity: number;
  orderType: 'INBOUND' | 'OUTBOUND';
  createdAt: string;
  userUuid: string;
};

export default function InventoryOrdersPage() {
  const [orders, setOrders] = useState<InventoryOrder[]>([]);
  const [isAuthorizing, setIsAuthorizing] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  const rows: OrderRow[] = orders.flatMap((order) => {
    if (order.items.length === 0) {
      return [
        {
          orderId: order.id,
          productName: '-',
          quantity: 0,
          orderType: order.type,
          createdAt: order.created_at,
          userUuid: order.created_by || '-',
        },
      ];
    }

    return order.items.map((item) => ({
      orderId: order.id,
      productName: item.name || `Product ${item.product_id}`,
      quantity: item.quantity,
      orderType: order.type,
      createdAt: order.created_at,
      userUuid: order.created_by || '-',
    }));
  });

  const loadOrders = async () => {
    setIsLoading(true);
    setError('');

    try {
      const response = await inventoryApi.getOrdersHistory();
      setOrders(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load Inbound Order and Outbound Order';
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
    void loadOrders();
  }, []);

  return (
    <main style={{ padding: '24px' }}>
      {isAuthorizing && <p>Redirecting to login...</p>}

      {!isAuthorizing && (
        <>
          <h1>Inbound Order and Outbound Order History</h1>
          <p>History of Inbound Order and Outbound Order records.</p>

          <button type="button" onClick={() => void loadOrders()} disabled={isLoading}>
          {isLoading ? 'Loading...' : 'Refresh Inbound Order and Outbound Order List'}
          </button>

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

          {!isLoading && !error && orders.length === 0 && (
          <p style={{ marginTop: '12px' }}>No Inbound Order or Outbound Order records found.</p>
          )}

          {!isLoading && !error && orders.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '16px' }}>
              <thead>
                <tr>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>name</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>quantity</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>type</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>created_at</th>
                  <th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>created_by</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const orderTypeUi = getOrderTypePresentation(row.orderType);

                  return (
                  <tr key={`${row.orderId}-${row.productName}-${index}`} style={{ background: orderTypeUi.rowAccent }}>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{row.productName}</td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{row.quantity}</td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '2px 10px',
                          borderRadius: '999px',
                          fontSize: '12px',
                          fontWeight: 700,
                          color: orderTypeUi.color,
                          background: orderTypeUi.background,
                          border: `1px solid ${orderTypeUi.border}`,
                        }}
                      >
                        <span aria-hidden="true">{orderTypeUi.icon}</span>
                        {orderTypeUi.label}
                      </span>
                    </td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{formatDate(row.createdAt)}</td>
                    <td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{row.userUuid}</td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </>
      )}
    </main>
  );
}
