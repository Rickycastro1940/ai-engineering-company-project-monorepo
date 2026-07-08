'use client';

import React, { useEffect, useState } from 'react';
import { inventoryApi, Product } from '../../../../../lib/inventory';

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

// Stock level thresholds:
// - Critical: current_stock <= 3
// - Low: current_stock <= 10
// - Healthy: current_stock > 10
const CRITICAL_STOCK_THRESHOLD = 3;
const LOW_STOCK_THRESHOLD = 10;

const getStockLevel = (currentStock: number) => {
	if (currentStock <= CRITICAL_STOCK_THRESHOLD) {
		return {
			label: 'Critical',
			color: '#b42318',
			background: '#fee4e2',
			border: '#fda29b',
		};
	}

	if (currentStock <= LOW_STOCK_THRESHOLD) {
		return {
			label: 'Low',
			color: '#b54708',
			background: '#fffaeb',
			border: '#fedf89',
		};
	}

	return {
		label: 'Healthy',
		color: '#067647',
		background: '#ecfdf3',
		border: '#abefc6',
	};
};

export default function InventoryProductsPage() {
	const [products, setProducts] = useState<Product[]>([]);
	const [isAuthorizing, setIsAuthorizing] = useState<boolean>(true);
	const [isLoading, setIsLoading] = useState<boolean>(true);
	const [isSubmittingOrder, setIsSubmittingOrder] = useState<boolean>(false);
	const [error, setError] = useState<string>('');
	const [notice, setNotice] = useState<string>('');

	const getRequestedQuantity = (productName: string, actionLabel: 'inbound' | 'outbound'): number | null => {
		const rawValue = window.prompt(`Enter ${actionLabel} quantity for ${productName}:`, '1');
		if (rawValue === null) {
			return null;
		}

		const parsed = Number.parseInt(rawValue, 10);
		if (!Number.isInteger(parsed) || parsed <= 0) {
			setError('Quantity must be a positive integer.');
			return null;
		}

		return parsed;
	};

	const submitOrder = async (product: Product, direction: 'inbound' | 'outbound') => {
		const quantity = getRequestedQuantity(product.name, direction);
		if (quantity === null) {
			return;
		}

		setIsSubmittingOrder(true);
		setError('');
		setNotice('');

		try {
			if (direction === 'inbound') {
				await inventoryApi.createInboundOrder({ product_id: product.id, quantity });
				setNotice(`Inbound Order created for ${product.name} with quantity ${quantity}.`);
			} else {
				await inventoryApi.createOutboundOrder({ product_id: product.id, quantity });
				setNotice(`Outbound Order created for ${product.name} with quantity ${quantity}.`);
			}

			await loadProducts();
		} catch (err) {
			const message = err instanceof Error
				? err.message
				: direction === 'inbound'
					? 'Failed to create Inbound Order'
					: 'Failed to create Outbound Order';
			setError(message);
		} finally {
			setIsSubmittingOrder(false);
		}
	};

	const loadProducts = async () => {
		setIsLoading(true);
		setError('');

		try {
			const response = await inventoryApi.getProducts();
			setProducts(response);
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Failed to load Products';
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
		void loadProducts();
	}, []);

	return (
		<main style={{ padding: '24px' }}>
			{isAuthorizing && <p>Redirecting to login...</p>}

			{!isAuthorizing && (
				<>
			<h1>Products</h1>
			<p>View Products and create Inbound Order or Outbound Order.</p>

			<button type="button" onClick={() => void loadProducts()} disabled={isLoading || isSubmittingOrder}>
				{isLoading ? 'Loading...' : 'Refresh Product List'}
			</button>

			{notice && (
				<p style={{ color: '#067647', marginTop: '12px' }}>
					{notice}
				</p>
			)}

			{error && (
				<p style={{ color: '#b42318', marginTop: '12px' }}>
					{error}
				</p>
			)}

			{!isLoading && !error && products.length === 0 && (
				<p style={{ marginTop: '12px' }}>No Products found.</p>
			)}

			{!isLoading && !error && products.length > 0 && (
				<table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '16px' }}>
					<thead>
						<tr>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>id</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>name</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>sku</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>category</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>unit</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>price</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>quantity</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>current_stock</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>Inbound Order</th>
							<th style={{ borderBottom: '1px solid #ccc', textAlign: 'left', padding: '8px' }}>Outbound Order</th>
						</tr>
					</thead>
					<tbody>
						{products.map((product) => {
							const stockLevel = getStockLevel(product.current_stock);

							return (
								<tr key={product.id}>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.id}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.name}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.sku}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.category}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.unit}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.price}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>{product.quantity}</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>
										<span
											style={{
												display: 'inline-flex',
												alignItems: 'center',
												gap: '8px',
												color: stockLevel.color,
												fontWeight: 700,
											}}
										>
											<span>{product.current_stock}</span>
											<span
												style={{
													display: 'inline-block',
													padding: '2px 10px',
													borderRadius: '999px',
													fontSize: '12px',
													fontWeight: 700,
													color: stockLevel.color,
													backgroundColor: stockLevel.background,
													border: `1px solid ${stockLevel.border}`,
												}}
											>
												{stockLevel.label}
											</span>
										</span>
									</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>
										<div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
											<a
												href={`/backoffice/inventory/orders/inbound?product_id=${product.id}`}
												style={{
													padding: '6px 10px',
													borderRadius: '6px',
													border: '1px solid #98a2b3',
													background: '#f8f9fc',
													color: '#344054',
													textDecoration: 'none',
													display: 'inline-flex',
													alignItems: 'center',
												}}
											>
												Open Inbound Order
											</a>
											<button
												type="button"
												onClick={() => void submitOrder(product, 'inbound')}
												disabled={isSubmittingOrder}
												style={{
													padding: '6px 10px',
													borderRadius: '6px',
													border: '1px solid #98a2b3',
													background: '#f8f9fc',
													cursor: 'pointer',
												}}
											>
												Create Inbound Order
											</button>
										</div>
									</td>
									<td style={{ borderBottom: '1px solid #eee', padding: '8px' }}>
										<div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
											<button
												type="button"
												onClick={() => void submitOrder(product, 'outbound')}
												disabled={isSubmittingOrder}
												style={{
													padding: '6px 10px',
													borderRadius: '6px',
													border: '1px solid #98a2b3',
													background: '#f8f9fc',
													cursor: 'pointer',
												}}
											>
												Create Outbound Order
											</button>
										</div>
									</td>
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