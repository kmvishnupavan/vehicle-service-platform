import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { LocationFreshness } from '../../realtime/types';

interface Coordinate {
  latitude: number;
  longitude: number;
  accuracy_meters?: number | null;
  label?: string;
}

interface Props {
  customerLocation?: Coordinate | null;
  mechanicLocation?: Coordinate | null;
  freshness: LocationFreshness;
}

// Custom SVG HTML Icons
const createCustomerIcon = () =>
  L.divIcon({
    className: 'custom-customer-marker',
    html: `
      <div style="position: relative; display: flex; flex-direction: column; align-items: center; transform: translate(-50%, -100%);">
        <div style="background-color: #4f46e5; color: white; padding: 7px; border-radius: 9999px; box-shadow: 0 4px 12px rgba(0,0,0,0.25); border: 2.5px solid white;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        </div>
        <div style="width: 0; height: 0; border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 7px solid #4f46e5; margin-top: -1px;"></div>
      </div>
    `,
    iconSize: [36, 42],
    iconAnchor: [18, 42],
  });

const createMechanicIcon = (isLive: boolean) =>
  L.divIcon({
    className: 'custom-mechanic-marker smooth-marker',
    html: `
      <div style="position: relative; display: flex; align-items: center; justify-content: center; transform: translate(-50%, -50%);">
        ${
          isLive
            ? '<div style="position: absolute; width: 44px; height: 44px; background: rgba(34,197,94,0.35); border-radius: 9999px; animation: ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>'
            : ''
        }
        <div style="position: relative; background-color: #16a34a; color: white; padding: 8px; border-radius: 9999px; box-shadow: 0 4px 14px rgba(22, 163, 74, 0.45); border: 2.5px solid white;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/>
            <circle cx="7" cy="17" r="2"/>
            <path d="M9 17h6"/>
            <circle cx="17" cy="17" r="2"/>
          </svg>
        </div>
      </div>
    `,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });

export const TrackingMap: React.FC<Props> = ({
  customerLocation,
  mechanicLocation,
  freshness,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const customerMarkerRef = useRef<L.Marker | null>(null);
  const mechanicMarkerRef = useRef<L.Marker | null>(null);
  const accuracyCircleRef = useRef<L.Circle | null>(null);
  const hasFittedBoundsRef = useRef<boolean>(false);

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    // Default center on India / city coordinates if uninitialized
    const initialCenter: [number, number] = customerLocation
      ? [customerLocation.latitude, customerLocation.longitude]
      : [17.385044, 78.486671];

    const map = L.map(mapContainerRef.current, {
      center: initialCenter,
      zoom: 14,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update Customer Marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (customerLocation?.latitude && customerLocation?.longitude) {
      const latLng: [number, number] = [customerLocation.latitude, customerLocation.longitude];

      if (!customerMarkerRef.current) {
        customerMarkerRef.current = L.marker(latLng, {
          icon: createCustomerIcon(),
          title: 'Service Destination',
        }).addTo(map);

        if (customerLocation.label) {
          customerMarkerRef.current.bindPopup(`<b>Destination</b><br/>${customerLocation.label}`);
        }
      } else {
        customerMarkerRef.current.setLatLng(latLng);
      }
    } else if (customerMarkerRef.current) {
      customerMarkerRef.current.remove();
      customerMarkerRef.current = null;
    }
  }, [customerLocation?.latitude, customerLocation?.longitude, customerLocation?.label]);

  // Update Mechanic Marker and Accuracy Circle
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (mechanicLocation?.latitude && mechanicLocation?.longitude) {
      const latLng: [number, number] = [mechanicLocation.latitude, mechanicLocation.longitude];
      const isLive = freshness === 'LIVE';

      if (!mechanicMarkerRef.current) {
        mechanicMarkerRef.current = L.marker(latLng, {
          icon: createMechanicIcon(isLive),
          title: 'Mechanic Location',
          zIndexOffset: 1000,
        }).addTo(map);
        mechanicMarkerRef.current.bindPopup('<b>Assigned Mechanic</b><br/>En route with live GPS');
      } else {
        mechanicMarkerRef.current.setIcon(createMechanicIcon(isLive));
        mechanicMarkerRef.current.setLatLng(latLng);
      }

      // Accuracy Circle
      if (mechanicLocation.accuracy_meters && mechanicLocation.accuracy_meters > 0) {
        if (!accuracyCircleRef.current) {
          accuracyCircleRef.current = L.circle(latLng, {
            radius: Number(mechanicLocation.accuracy_meters),
            color: '#16a34a',
            fillColor: '#22c55e',
            fillOpacity: 0.12,
            weight: 1,
          }).addTo(map);
        } else {
          accuracyCircleRef.current.setLatLng(latLng);
          accuracyCircleRef.current.setRadius(Number(mechanicLocation.accuracy_meters));
        }
      } else if (accuracyCircleRef.current) {
        accuracyCircleRef.current.remove();
        accuracyCircleRef.current = null;
      }
    } else {
      if (mechanicMarkerRef.current) {
        mechanicMarkerRef.current.remove();
        mechanicMarkerRef.current = null;
      }
      if (accuracyCircleRef.current) {
        accuracyCircleRef.current.remove();
        accuracyCircleRef.current = null;
      }
    }
  }, [mechanicLocation?.latitude, mechanicLocation?.longitude, mechanicLocation?.accuracy_meters, freshness]);

  // Initial Bounds Auto-Fitting (Once only, avoids continuous recentering)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || hasFittedBoundsRef.current) return;

    const points: [number, number][] = [];
    if (customerLocation?.latitude && customerLocation?.longitude) {
      points.push([customerLocation.latitude, customerLocation.longitude]);
    }
    if (mechanicLocation?.latitude && mechanicLocation?.longitude) {
      points.push([mechanicLocation.latitude, mechanicLocation.longitude]);
    }

    if (points.length >= 2) {
      const bounds = L.latLngBounds(points);
      map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16 });
      hasFittedBoundsRef.current = true;
    } else if (points.length === 1) {
      map.setView(points[0], 14);
      hasFittedBoundsRef.current = true;
    }
  }, [customerLocation?.latitude, customerLocation?.longitude, mechanicLocation?.latitude, mechanicLocation?.longitude]);

  return (
    <div className="relative w-full h-full min-h-[380px] bg-slate-100 rounded-xl overflow-hidden border border-slate-200 shadow-inner">
      <div ref={mapContainerRef} className="w-full h-full min-h-[380px]" />
    </div>
  );
};
