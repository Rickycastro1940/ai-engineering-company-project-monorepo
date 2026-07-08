'use client';

import React, { useEffect, useState } from 'react';
import { inventoryApi, Product } from '../../../../../../lib/inventory';

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

const isInsufficientStockError = (message: string): boolean => {
  const normalized = message.toLowerCase();
  return normalized.includes('400') && normalized.includes('insufficient stock');
};

export default function InventoryInboundOrderPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string>('');
  const [selectedProductStock, setSelectedProductStock] = useState<number | null>(null);
  const [isLoadingSelectedStock, setIsLoadingSelectedStock] = useState<boolean>(false);
  const [selectedStockError, setSelectedStockError] = useState<string>('');
  const [quantity, setQuantity] = useState<string>('1');
  const [isLoadingProducts, setIsLoadingProducts] = useState<boolean>(true);
  const [isAuthorizing, setIsAuthorizing] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [quantityError, setQuantityError] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string>('');
  const parsedQuantity = Number.parseInt(quantity, 10);
  const exceedsDisplayedStock =
    selectedProductStock !== null && Number.isInteger(parsedQuantity) && parsedQuantity > selectedProductStock;

  const loadProducts = async () => {
    setIsLoadingProducts(true);
    setError('');

    try {
      const response = await inventoryApi.getProducts();
      const sortedProducts = [...response].sort((a, b) => a.name.localeCompare(b.name));
      setProducts(sortedProducts);

      const params = new URLSearchParams(window.location.search);
      const productIdParam = params.get('product_id');
      const requestedProductId = productIdParam ? Number.parseInt(productIdParam, 10) : NaN;
      const hasRequestedProduct = sortedProducts.some((product) => product.id === requestedProductId);

      if (hasRequestedProduct) {
        setSelectedProductId(String(requestedProductId));
      } else {
        setSelectedProductId('');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load Products';
      setError(message);
    } finally {
      setIsLoadingProducts(false);
    }
  };

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      window.location.replace(LOGIN_PATH);
      return;
    }

    setIsAuthorizing(false);
    void loadProducts();
  }, []);

  useEffect(() => {
    if (!selectedProductId) {
      setSelectedProductStock(null);
      setSelectedStockError('');
      return;
    }

    let isActive = true;

    const loadSelectedStock = async () => {
      setIsLoadingSelectedStock(true);
      setSelectedStockError('');

      try {
        const product = await inventoryApi.getProductById(Number.parseInt(selectedProductId, 10));
        if (isActive) {
          setSelectedProductStock(product.current_stock);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load current_stock';
        if (isActive) {
          setSelectedProductStock(null);
          setSelectedStockError(message);
        }
      } finally {
        if (isActive) {
          setIsLoadingSelectedStock(false);
        }
      }
    };

    void loadSelectedStock();

    return () => {
      isActive = false;
    };
  }, [selectedProductId]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setQuantityError('');
    setSuccessMessage('');

    const productId = Number.parseInt(selectedProductId, 10);
    const parsedQuantity = Number.parseInt(quantity, 10);

    if (!Number.isInteger(productId) || productId <= 0) {
      setError('Please select a valid Product.');
      return;
    }

    if (!Number.isInteger(parsedQuantity) || parsedQuantity <= 0) {
      setQuantityError('Quantity must be a positive integer.');
      return;
    }

    setIsSubmitting(true);

    try {
      await inventoryApi.createInboundOrder({
        product_id: productId,
        quantity: parsedQuantity,
      });
      setSuccessMessage('Inbound Order submitted successfully.');
      setSelectedProductId('');
      setSelectedProductStock(null);
      setQuantity('');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to submit Inbound Order';
      if (isInsufficientStockError(message)) {
        setQuantityError(message);
      } else {
        setError(message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main style={{ maxWidth: '640px', padding: '24px' }}>
      {isAuthorizing && <p>Redirecting to login...</p>}

      {!isAuthorizing && (
      <>
      <h1>Inbound Order</h1>
      <p>Create an Inbound Order.</p>

      <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '12px', marginTop: '16px' }}>
        <label htmlFor="productId">name</label>
        <select
          id="productId"
          value={selectedProductId}
          onChange={(event) => setSelectedProductId(event.target.value)}
          disabled={isLoadingProducts || isSubmitting || products.length === 0}
        >
          {products.length === 0 ? (
            <option value="">No Products available</option>
          ) : (
            <>
              <option value="">Select a Product by name</option>
              {products.map((product) => (
                <option key={product.id} value={String(product.id)}>
                  {product.name} (SKU: {product.sku})
                </option>
              ))}
            </>
          )}
        </select>

        {selectedProductId && (
          <div
            style={{
              color: '#344054',
              background: '#f9fafb',
              border: '1px solid #d0d5dd',
              borderRadius: '8px',
              padding: '10px 12px',
            }}
          >
                {isLoadingSelectedStock && 'Loading current_stock...'}
                {!isLoadingSelectedStock && selectedStockError && `current_stock unavailable: ${selectedStockError}`}
            {!isLoadingSelectedStock && !selectedStockError && selectedProductStock !== null && (
              <>current_stock: <strong>{selectedProductStock}</strong></>
            )}
          </div>
        )}

        <label htmlFor="quantity">quantity</label>
        <input
          id="quantity"
          type="number"
          min="1"
          step="1"
          value={quantity}
          onChange={(event) => {
            setQuantity(event.target.value);
            setQuantityError('');
          }}
          disabled={isSubmitting || !selectedProductId || isLoadingSelectedStock}
        />

        {quantityError && (
          <div
            role="alert"
            aria-live="assertive"
            style={{
              color: '#b42318',
              background: '#fee4e2',
              border: '1px solid #fda29b',
              borderRadius: '8px',
              padding: '10px 12px',
              fontWeight: 600,
            }}
          >
            {quantityError}
          </div>
        )}

        {exceedsDisplayedStock && (
          <div
            role="alert"
            aria-live="polite"
            style={{
              color: '#b54708',
              background: '#fffaeb',
              border: '1px solid #fedf89',
              borderRadius: '8px',
              padding: '10px 12px',
              fontWeight: 600,
            }}
          >
            Warning: entered quantity exceeds displayed current_stock. You can still submit, but the API will enforce the final rule.
          </div>
        )}

        <button type="submit" disabled={isLoadingProducts || isSubmitting || products.length === 0 || !selectedProductId || isLoadingSelectedStock}>
          {isSubmitting ? 'Submitting...' : 'Submit Inbound Order'}
        </button>
      </form>

      {successMessage && (
        <div
          role="status"
          aria-live="polite"
          style={{
            marginTop: '12px',
            color: '#067647',
            background: '#ecfdf3',
            border: '1px solid #abefc6',
            borderRadius: '8px',
            padding: '10px 12px',
          }}
        >
          {successMessage}
        </div>
      )}
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
      </>
      )}
    </main>
  );
}
