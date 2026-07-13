'use client';

import { useState, useEffect } from 'react';
import { inventoryApi } from '../../../../../../../lib/inventory';
import { Product } from '../../../../../../../lib/types';
import { useRouter } from 'next/navigation';

export default function OutboundOrderPage() {
    const [products, setProducts] = useState<Product[]>([]);
    const [selectedProductId, setSelectedProductId] = useState('');
    const [quantity, setQuantity] = useState(1);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
    const router = useRouter();

    useEffect(() => {
        const fetchProducts = async () => {
            try {
                const data = await inventoryApi.getProducts();
                setProducts(data);
            } catch (err) {
                console.error('Failed to fetch products:', err);
            }
        };
        fetchProducts();
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);

        try {
            await inventoryApi.createOutboundOrder({
                product_id: selectedProductId,
                quantity: quantity
            });
            setMessage({ type: 'success', text: 'Outbound order created successfully!' });
            setSelectedProductId('');
            setQuantity(1);
        } catch (err: any) {
            setMessage({ type: 'error', text: err.message || 'Failed to create outbound order' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-6">
            <h1 className="text-2xl font-bold mb-6">Outbound Order (Consumption)</h1>
            <form onSubmit={handleSubmit} className="max-w-md space-y-4">
                <div>
                    <label className="block text-sm font-medium mb-1">Product</label>
                    <select
                        value={selectedProductId}
                        onChange={(e) => setSelectedProductId(e.target.value)}
                        required
                        className="w-full border rounded p-2 text-black"
                    >
                        <option value="">Select a product</option>
                        {products.map((p) => (
                            <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">Quantity to Consume</label>
                    <input
                        type="number"
                        value={quantity}
                        onChange={(e) => setQuantity(parseInt(e.target.value))}
                        min="1"
                        required
                        className="w-full border rounded p-2 text-black"
                    />
                </div>

                {message && (
                    <div className={}>
                        {message.text}
                    </div>
                )}

                <button
                    type="submit"
                    disabled={loading}
                    className="w-full bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600 disabled:bg-gray-400"
                >
                    {loading ? 'Processing...' : 'Submit Outbound Order'}
                </button>
            </form>
        </div>
    );
}
