import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { CatalogServiceItem, ServiceCategory, ServicePricingTier } from '../types/customerBooking';

export const serviceKeys = {
  all: ['services'] as const,
  categories: () => [...serviceKeys.all, 'categories'] as const,
  items: (params?: { categoryId?: string; vehicleTypeId?: string }) =>
    [...serviceKeys.all, 'items', params?.categoryId || '', params?.vehicleTypeId || ''] as const,
  price: (serviceId?: string, vehicleTypeId?: string) =>
    [...serviceKeys.all, 'price', serviceId || '', vehicleTypeId || ''] as const,
};

export function useServiceCategories() {
  return useQuery<ServiceCategory[]>({
    queryKey: serviceKeys.categories(),
    queryFn: () => api.get<ServiceCategory[]>('/services/categories'),
    staleTime: 60_000 * 5,
  });
}

export function useCatalogServices(params?: { categoryId?: string; vehicleTypeId?: string }) {
  return useQuery<CatalogServiceItem[]>({
    queryKey: serviceKeys.items(params),
    queryFn: () => {
      const searchParams = new URLSearchParams();
      if (params?.categoryId) searchParams.append('category_id', params.categoryId);
      if (params?.vehicleTypeId) searchParams.append('vehicle_type_id', params.vehicleTypeId);
      const queryStr = searchParams.toString();
      return api.get<CatalogServiceItem[]>(`/services/items${queryStr ? `?${queryStr}` : ''}`);
    },
    staleTime: 60_000 * 5,
  });
}

export function useServicePrice(serviceId?: string, vehicleTypeId?: string) {
  return useQuery<ServicePricingTier>({
    queryKey: serviceKeys.price(serviceId, vehicleTypeId),
    queryFn: () => {
      if (!serviceId || !vehicleTypeId) throw new Error('Missing serviceId or vehicleTypeId');
      return api.get<ServicePricingTier>(
        `/services/${serviceId}/price?vehicle_type_id=${vehicleTypeId}`
      );
    },
    enabled: Boolean(serviceId && vehicleTypeId),
    staleTime: 60_000 * 5,
  });
}
