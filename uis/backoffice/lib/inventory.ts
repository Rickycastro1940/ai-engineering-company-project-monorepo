import axios from 'axios';

const inventoryApi = axios.create({
  baseURL: process.env.NEXT_PUBLIC_INVENTORY_API_URL,
});

export default inventoryApi;
