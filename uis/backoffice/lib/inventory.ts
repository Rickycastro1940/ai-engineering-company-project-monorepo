const BASE_URL = process.env.NEXT_PUBLIC_INVENTORY_API_URL || 'http://localhost:8000';

const TOKEN_KEYS = ['token', 'access_token', 'authToken'];

const getCookieValue = (name: string): string | null => {
  if (typeof document === 'undefined') {
    return null;
  }
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
};

const getAuthToken = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }

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

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  requiresAuth: boolean = true,
): Promise<T> {
  const token = getAuthToken();
  if (requiresAuth && !token) {
    throw new Error('Missing auth token for protected endpoint');
  }

  const headers = new Headers(options.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  headers.set('Content-Type', 'application/json');

  const config: RequestInit = { ...options, headers };
  const response = await fetch(`${BASE_URL}${endpoint}`, config);

  if (response.status >= 400 && response.status < 600) {
    const contentType = response.headers.get('content-type') || '';
    const rawBody = await response.text();

    let messageFromBody = '';
    if (rawBody) {
      if (contentType.includes('application/json')) {
        try {
          const parsed = JSON.parse(rawBody);
          if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
            messageFromBody = parsed.detail;
          } else if (typeof parsed?.message === 'string' && parsed.message.trim()) {
            messageFromBody = parsed.message;
          } else {
            messageFromBody = JSON.stringify(parsed);
          }
        } catch (error) {
          const parseReason = error instanceof Error ? error.message : 'Unknown JSON parse error';
          messageFromBody = `Malformed JSON error body: ${rawBody}. Parse error: ${parseReason}`;
        }
      } else {
        messageFromBody = rawBody;
      }
    }

    const statusSummary = `HTTP ${response.status} ${response.statusText}`.trim();
    const errorMessage = messageFromBody
      ? `${statusSummary}: ${messageFromBody}`
      : `${statusSummary}: Request failed and response body was empty`;

    throw new Error(errorMessage);
  }

  if (!response.ok) {
    throw new Error(`Unexpected HTTP status ${response.status} ${response.statusText}`.trim());
  }

  return response.status === 204 ? ({} as T) : response.json();
}

export interface Product {
  id: number;
  name: string;
  sku: string;
  category: string;
  price: number;
  quantity: number;
  unit: string;
  current_stock: number;
}

export interface OrderItem {
  product_id: number;
  quantity: number;
  sku?: string;
  name?: string;
  unit?: string;
  price?: number;
}

export interface InventoryOrder {
  id: string;
  type: 'INBOUND' | 'OUTBOUND';
  created_by: string;
  created_at: string;
  items: OrderItem[];
}

type ApiProduct = Partial<Product> & {
  product_id?: string | number;
};

type ApiOrderItem = Partial<OrderItem> & {
  product_id?: string | number;
};

type ApiInventoryOrder = Partial<InventoryOrder> & {
  id?: string | number;
  items?: ApiOrderItem[];
};

const toNumber = (value: unknown, fallback: number = 0): number => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
};

const normalizeProduct = (raw: ApiProduct): Product => {
  const currentStock = toNumber(raw.current_stock, 0);
  const id = raw.id !== undefined ? toNumber(raw.id, 0) : toNumber(raw.product_id, 0);

  return {
    id,
    name: raw.name ?? '',
    sku: raw.sku ?? '',
    category: raw.category ?? '-',
    price: toNumber(raw.price, 0),
    quantity: raw.quantity !== undefined ? toNumber(raw.quantity, 0) : currentStock,
    unit: raw.unit ?? '-',
    current_stock: currentStock,
  };
};

const normalizeOrderItem = (raw: ApiOrderItem): OrderItem => ({
  product_id: toNumber(raw.product_id, 0),
  quantity: toNumber(raw.quantity, 0),
  sku: raw.sku,
  name: raw.name,
  unit: raw.unit,
  price: raw.price !== undefined ? toNumber(raw.price, 0) : undefined,
});

const normalizeInventoryOrder = (raw: ApiInventoryOrder): InventoryOrder => ({
  id: String(raw.id ?? ''),
  type: raw.type === 'INBOUND' ? 'INBOUND' : 'OUTBOUND',
  created_by: raw.created_by ?? '',
  created_at: raw.created_at ?? '',
  items: Array.isArray(raw.items) ? raw.items.map(normalizeOrderItem) : [],
});

export const inventoryApi = {
  getProducts: async (): Promise<Product[]> => {
    const data = await apiRequest<ApiProduct[]>('/inventory/products');
    return data.map(normalizeProduct);
  },
  getProductById: async (id: number): Promise<Product> => {
    const data = await apiRequest<ApiProduct>(`/inventory/products/${id}`);
    return normalizeProduct(data);
  },
  createInboundOrder: (data: { product_id: number; quantity: number }) =>
    apiRequest('/inventory/orders/inbound', { method: 'POST', body: JSON.stringify(data) }),
  createOutboundOrder: (data: { product_id: number; quantity: number }) =>
    apiRequest('/inventory/orders/outbound', { method: 'POST', body: JSON.stringify(data) }),
  getOrdersHistory: async (): Promise<InventoryOrder[]> => {
    const data = await apiRequest<ApiInventoryOrder[]>('/inventory/orders');
    return data.map(normalizeInventoryOrder);
  },
};
