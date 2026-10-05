import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Car,
  Bike,
  MapPin,
  Calendar,
  Clock,
  CheckCircle,
  Plus,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  Shield,
  Receipt,
} from 'lucide-react';
import {
  useMyVehicles,
  useVehicleTypes,
  useVehicleMakes,
  useBrandModels,
  useCreateVehicle,
} from '../hooks/useVehicles';
import { useServiceCategories, useCatalogServices } from '../hooks/useServiceCatalog';
import { useMyAddresses, useCreateAddress } from '../hooks/useAddresses';
import { useCreateBooking } from '../hooks/useCreateBooking';
import {
  CustomerVehicle,
  CatalogServiceItem,
  CustomerAddress,
} from '../types/customerBooking';

const STEPS = [
  { id: 1, label: 'Vehicle' },
  { id: 2, label: 'Services' },
  { id: 3, label: 'Location' },
  { id: 4, label: 'Timing' },
  { id: 5, label: 'Review' },
];

export const BookServicePage: React.FC = () => {
  const navigate = useNavigate();

  // Wizard Navigation
  const [currentStep, setCurrentStep] = useState<number>(1);

  // Step 1: Vehicle State
  const { data: myVehicles = [], isLoading: isLoadingVehicles } = useMyVehicles();
  const [selectedVehicle, setSelectedVehicle] = useState<CustomerVehicle | null>(null);
  const [showAddVehicle, setShowAddVehicle] = useState<boolean>(false);
  const [newVehicleTypeId, setNewVehicleTypeId] = useState<string>('');
  const [newBrandId, setNewBrandId] = useState<string>('');
  const [newModelId, setNewModelId] = useState<string>('');
  const [newRegNumber, setNewRegNumber] = useState<string>('');
  const [newYear, setNewYear] = useState<string>('2022');
  const [newFuelType, setNewFuelType] = useState<string>('petrol');

  const { data: vehicleTypes = [] } = useVehicleTypes();
  const { data: brands = [] } = useVehicleMakes();
  const { data: models = [] } = useBrandModels(newBrandId || undefined);
  const createVehicleMutation = useCreateVehicle();

  // Step 2: Service Selection State
  const [selectedCategorySlug, setSelectedCategorySlug] = useState<string>('all');
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([]);
  const { data: categories = [] } = useServiceCategories();
  const { data: allServices = [], isLoading: isLoadingServices } = useCatalogServices({
    vehicleTypeId: selectedVehicle?.vehicle_type_id,
  });

  // Step 3: Location State
  const { data: myAddresses = [], isLoading: isLoadingAddresses } = useMyAddresses();
  const [selectedAddress, setSelectedAddress] = useState<CustomerAddress | null>(null);
  const [showAddAddress, setShowAddAddress] = useState<boolean>(false);
  const [newAddressLabel, setNewAddressLabel] = useState<string>('Home');
  const [newAddressLine, setNewAddressLine] = useState<string>('');
  const [newArea, setNewArea] = useState<string>('');
  const [newCity, setNewCity] = useState<string>('Bengaluru');
  const [newState, setNewState] = useState<string>('Karnataka');
  const [newPostalCode, setNewPostalCode] = useState<string>('');
  const [newLatitude, setNewLatitude] = useState<number>(12.9716);
  const [newLongitude, setNewLongitude] = useState<number>(77.5946);
  const createAddressMutation = useCreateAddress();

  // Step 4: Timing State
  const [timingType, setTimingType] = useState<'immediate' | 'scheduled'>('immediate');
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const [scheduledDate, setScheduledDate] = useState<string>(tomorrow.toISOString().split('T')[0]);
  const [scheduledTime, setScheduledTime] = useState<string>('10:00');
  const [customerNotes, setCustomerNotes] = useState<string>('');

  // Step 5: Submission State
  const createBookingMutation = useCreateBooking();
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  // Auto-select primary or first vehicle if available
  useEffect(() => {
    if (!selectedVehicle && myVehicles.length > 0) {
      const primary = myVehicles.find((v) => v.is_primary) || myVehicles[0];
      setSelectedVehicle(primary);
    }
  }, [myVehicles, selectedVehicle]);

  // Auto-select default address if available
  useEffect(() => {
    if (!selectedAddress && myAddresses.length > 0) {
      const defaultAddr = myAddresses.find((a) => a.is_default) || myAddresses[0];
      setSelectedAddress(defaultAddr);
    }
  }, [myAddresses, selectedAddress]);

  // Attempt to get user's current GPS location for new address
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setNewLatitude(pos.coords.latitude);
          setNewLongitude(pos.coords.longitude);
        },
        () => {
          // Defaults already set
        },
        { timeout: 5000 }
      );
    }
  }, []);

  // Filtered services
  const filteredServices = allServices.filter((svc) => {
    if (selectedCategorySlug === 'all') return true;
    const cat = categories.find((c) => c.slug === selectedCategorySlug);
    return cat ? svc.category_id === cat.id : true;
  });

  // Calculate price helper
  const getServicePrice = (svc: CatalogServiceItem): number => {
    const tier = svc.pricing?.find(
      (p) => p.vehicle_type_id === selectedVehicle?.vehicle_type_id
    ) || svc.pricing?.[0];
    return tier ? parseFloat(String(tier.base_price)) : 0;
  };

  const selectedServicesList = allServices.filter((s) => selectedServiceIds.includes(s.id));
  const estimatedSubtotal = selectedServicesList.reduce((acc, s) => acc + getServicePrice(s), 0);
  const estimatedGst = Math.round(estimatedSubtotal * 0.18 * 100) / 100;
  const estimatedTotal = estimatedSubtotal + estimatedGst;

  // Validation rules per step
  const isStepValid = (step: number): boolean => {
    switch (step) {
      case 1:
        return Boolean(selectedVehicle);
      case 2:
        return selectedServiceIds.length > 0;
      case 3:
        return Boolean(selectedAddress);
      case 4:
        if (timingType === 'scheduled') {
          return Boolean(scheduledDate && scheduledTime);
        }
        return true;
      case 5:
        return Boolean(selectedVehicle && selectedServiceIds.length > 0 && selectedAddress);
      default:
        return false;
    }
  };

  // Add Vehicle Handler
  const handleAddNewVehicle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newVehicleTypeId || !newBrandId || !newModelId || !newRegNumber) return;

    try {
      const created = await createVehicleMutation.mutateAsync({
        vehicle_type_id: newVehicleTypeId,
        brand_id: newBrandId,
        model_id: newModelId,
        registration_number: newRegNumber.trim().toUpperCase(),
        manufacture_year: parseInt(newYear) || 2022,
        fuel_type: newFuelType,
        is_primary: myVehicles.length === 0,
      });
      setSelectedVehicle(created);
      setShowAddVehicle(false);
      setNewRegNumber('');
    } catch (err: any) {
      alert(err?.message || 'Failed to register vehicle. Please check inputs.');
    }
  };

  // Add Address Handler
  const handleAddNewAddress = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAddressLine || !newArea || !newCity || !newPostalCode) return;

    try {
      const created = await createAddressMutation.mutateAsync({
        label: newAddressLabel,
        address_line: newAddressLine,
        area: newArea,
        city: newCity,
        state: newState,
        postal_code: newPostalCode,
        latitude: newLatitude,
        longitude: newLongitude,
        is_default: myAddresses.length === 0,
      });
      setSelectedAddress(created);
      setShowAddAddress(false);
      setNewAddressLine('');
      setNewArea('');
      setNewPostalCode('');
    } catch (err: any) {
      alert(err?.message || 'Failed to save address.');
    }
  };

  // Service toggle helper
  const toggleService = (serviceId: string) => {
    setSelectedServiceIds((prev) =>
      prev.includes(serviceId) ? prev.filter((id) => id !== serviceId) : [...prev, serviceId]
    );
  };

  // Final Booking Confirmation Submission
  const handleConfirmBooking = async () => {
    if (!selectedVehicle || !selectedAddress || selectedServiceIds.length === 0) return;
    setSubmissionError(null);

    let finalScheduledAt: string | null = null;
    if (timingType === 'scheduled') {
      finalScheduledAt = new Date(`${scheduledDate}T${scheduledTime}:00`).toISOString();
    }

    try {
      const booking = await createBookingMutation.mutateAsync({
        vehicle_id: selectedVehicle.id,
        address_id: selectedAddress.id,
        items: selectedServiceIds.map((id) => ({
          service_id: id,
          quantity: 1,
        })),
        scheduled_at: finalScheduledAt,
        customer_notes: customerNotes.trim() || undefined,
      });

      // Navigate to booking details
      navigate(`/bookings/${booking.id}`);
    } catch (err: any) {
      setSubmissionError(err?.message || 'Failed to create booking. Please try again.');
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Wizard Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-5">
        <div>
          <Link
            to="/customer/dashboard"
            className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-slate-800 mb-2 transition"
          >
            <ArrowLeft className="w-3.5 h-3.5 mr-1" />
            Back to Dashboard
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Book Vehicle Service</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Book professional doorstep service with live mechanic dispatch & tracking
          </p>
        </div>
      </div>

      {/* Progress Stepper Bar */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-xs">
        <div className="flex items-center justify-between max-w-2xl mx-auto relative">
          <div className="absolute top-1/2 left-4 right-4 h-0.5 bg-slate-200 -translate-y-1/2 z-0" />
          {STEPS.map((s) => {
            const isCompleted = currentStep > s.id;
            const isCurrent = currentStep === s.id;
            return (
              <div key={s.id} className="relative z-10 flex flex-col items-center">
                <button
                  type="button"
                  onClick={() => {
                    if (s.id < currentStep) setCurrentStep(s.id);
                  }}
                  disabled={s.id > currentStep}
                  className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold transition ${
                    isCompleted
                      ? 'bg-emerald-600 text-white shadow-xs'
                      : isCurrent
                      ? 'bg-slate-900 text-white ring-4 ring-slate-100'
                      : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                  }`}
                >
                  {isCompleted ? <CheckCircle className="w-4 h-4" /> : s.id}
                </button>
                <span
                  className={`text-[11px] font-semibold mt-1.5 ${
                    isCurrent ? 'text-slate-900' : 'text-slate-400'
                  }`}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Step Content */}
      <div className="bg-white border border-slate-200 rounded-3xl p-6 sm:p-8 shadow-sm">
        {/* STEP 1: VEHICLE SELECTION */}
        {currentStep === 1 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-900">Step 1: Choose Your Vehicle</h2>
                <p className="text-xs text-slate-500">
                  Select an enrolled vehicle or register a new bike or car
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowAddVehicle(!showAddVehicle)}
                className="inline-flex items-center px-3 py-1.5 rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-800 text-xs font-bold hover:bg-emerald-100 transition"
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                {showAddVehicle ? 'Cancel' : 'Add Vehicle'}
              </button>
            </div>

            {/* Add Vehicle Inline Drawer */}
            {showAddVehicle && (
              <form
                onSubmit={handleAddNewVehicle}
                className="bg-slate-50 border border-slate-200 rounded-2xl p-5 space-y-4 text-xs animate-in fade-in"
              >
                <h3 className="font-bold text-slate-900 text-sm">Register New Vehicle</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Vehicle Type</label>
                    <select
                      value={newVehicleTypeId}
                      onChange={(e) => {
                        setNewVehicleTypeId(e.target.value);
                        setNewBrandId('');
                        setNewModelId('');
                      }}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    >
                      <option value="">Select Type</option>
                      {vehicleTypes.map((vt) => (
                        <option key={vt.id} value={vt.id}>
                          {vt.name.toUpperCase()}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Brand / Make</label>
                    <select
                      value={newBrandId}
                      onChange={(e) => {
                        setNewBrandId(e.target.value);
                        setNewModelId('');
                      }}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    >
                      <option value="">Select Brand</option>
                      {brands.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Model</label>
                    <select
                      value={newModelId}
                      onChange={(e) => setNewModelId(e.target.value)}
                      required
                      disabled={!newBrandId}
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl disabled:bg-slate-100"
                    >
                      <option value="">Select Model</option>
                      {models.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Registration Number
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. KA01AB1234"
                      value={newRegNumber}
                      onChange={(e) => setNewRegNumber(e.target.value)}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl uppercase font-mono"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Manufacture Year
                    </label>
                    <input
                      type="number"
                      value={newYear}
                      onChange={(e) => setNewYear(e.target.value)}
                      min="1990"
                      max="2026"
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Fuel Type</label>
                    <select
                      value={newFuelType}
                      onChange={(e) => setNewFuelType(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl capitalize"
                    >
                      <option value="petrol">Petrol</option>
                      <option value="diesel">Diesel</option>
                      <option value="electric">Electric</option>
                      <option value="cng">CNG</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={createVehicleMutation.isPending}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl shadow-xs transition"
                  >
                    {createVehicleMutation.isPending ? 'Saving...' : 'Save & Select Vehicle'}
                  </button>
                </div>
              </form>
            )}

            {/* Existing Vehicles Grid */}
            {isLoadingVehicles ? (
              <div className="py-12 flex justify-center">
                <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : myVehicles.length === 0 ? (
              <div className="border-2 border-dashed border-slate-200 rounded-2xl p-8 text-center space-y-3">
                <Car className="w-10 h-10 text-slate-300 mx-auto" />
                <h4 className="font-bold text-slate-700">No vehicles registered yet</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Click "Add Vehicle" above to register your vehicle and proceed with your service
                  booking.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {myVehicles.map((vehicle) => {
                  const isSelected = selectedVehicle?.id === vehicle.id;
                  const isBike =
                    vehicle.vehicle_types?.name === 'bike' ||
                    vehicle.vehicle_models?.name?.toLowerCase().includes('activa') ||
                    vehicle.vehicle_models?.name?.toLowerCase().includes('pulsar');

                  return (
                    <div
                      key={vehicle.id}
                      onClick={() => setSelectedVehicle(vehicle)}
                      className={`p-4 rounded-2xl border-2 transition cursor-pointer flex items-center justify-between ${
                        isSelected
                          ? 'border-emerald-600 bg-emerald-50/40 shadow-xs'
                          : 'border-slate-200 hover:border-slate-300 bg-white'
                      }`}
                    >
                      <div className="flex items-center space-x-3.5">
                        <div
                          className={`p-3 rounded-xl ${
                            isSelected
                              ? 'bg-emerald-600 text-white'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {isBike ? <Bike className="w-6 h-6" /> : <Car className="w-6 h-6" />}
                        </div>
                        <div>
                          <span className="text-[11px] font-mono font-bold text-slate-500 uppercase">
                            {vehicle.registration_number}
                          </span>
                          <h4 className="font-bold text-slate-900 text-sm">
                            {vehicle.vehicle_brands?.name} {vehicle.vehicle_models?.name}
                          </h4>
                          <span className="text-[11px] text-slate-500 capitalize">
                            {vehicle.fuel_type} • {vehicle.manufacture_year || '2022'}
                          </span>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                          isSelected ? 'border-emerald-600 bg-emerald-600' : 'border-slate-300'
                        }`}
                      >
                        {isSelected && <div className="w-2 h-2 rounded-full bg-white" />}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* STEP 2: SERVICE SELECTION */}
        {currentStep === 2 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Step 2: Select Required Services</h2>
              <p className="text-xs text-slate-500">
                Choose the service packages you want performed on your{' '}
                <span className="font-semibold text-slate-800">
                  {selectedVehicle?.vehicle_brands?.name} {selectedVehicle?.vehicle_models?.name} (
                  {selectedVehicle?.registration_number})
                </span>
              </p>
            </div>

            {/* Category Pills */}
            <div className="flex flex-wrap gap-2 pb-2 border-b border-slate-100">
              <button
                type="button"
                onClick={() => setSelectedCategorySlug('all')}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition ${
                  selectedCategorySlug === 'all'
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                All Services
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setSelectedCategorySlug(cat.slug)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition ${
                    selectedCategorySlug === cat.slug
                      ? 'bg-slate-900 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {cat.name}
                </button>
              ))}
            </div>

            {/* Services Cards */}
            {isLoadingServices ? (
              <div className="py-12 flex justify-center">
                <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : filteredServices.length === 0 ? (
              <div className="p-8 text-center text-slate-500 border border-slate-100 rounded-2xl">
                No services found for this category and vehicle combination.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {filteredServices.map((svc) => {
                  const isSelected = selectedServiceIds.includes(svc.id);
                  const price = getServicePrice(svc);

                  return (
                    <div
                      key={svc.id}
                      onClick={() => toggleService(svc.id)}
                      className={`p-5 rounded-2xl border-2 transition cursor-pointer flex flex-col justify-between ${
                        isSelected
                          ? 'border-emerald-600 bg-emerald-50/40 shadow-xs'
                          : 'border-slate-200 hover:border-slate-300 bg-white'
                      }`}
                    >
                      <div className="space-y-2">
                        <div className="flex items-start justify-between">
                          <h4 className="font-bold text-slate-900 text-sm leading-snug">
                            {svc.name}
                          </h4>
                          <span className="text-base font-extrabold text-slate-900 ml-2 shrink-0">
                            ₹{price.toFixed(2)}
                          </span>
                        </div>
                        {svc.description && (
                          <p className="text-xs text-slate-600 leading-relaxed line-clamp-2">
                            {svc.description}
                          </p>
                        )}
                      </div>

                      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                        <span className="flex items-center space-x-1">
                          <Clock className="w-3.5 h-3.5 text-slate-400" />
                          <span>~{svc.estimated_duration_minutes} mins</span>
                        </span>
                        <div
                          className={`px-2.5 py-1 rounded-lg font-bold text-xs transition ${
                            isSelected
                              ? 'bg-emerald-600 text-white'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {isSelected ? 'Selected ✓' : '+ Add'}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Running Total Preview */}
            {selectedServiceIds.length > 0 && (
              <div className="bg-slate-900 text-white rounded-2xl p-4 flex items-center justify-between shadow-md">
                <div>
                  <span className="text-xs text-slate-400">
                    {selectedServiceIds.length} service{selectedServiceIds.length > 1 ? 's' : ''}{' '}
                    selected
                  </span>
                  <div className="text-lg font-bold">Estimated ₹{estimatedTotal.toFixed(2)}</div>
                </div>
                <button
                  type="button"
                  onClick={() => setCurrentStep(3)}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition flex items-center"
                >
                  <span>Select Location</span>
                  <ArrowRight className="w-4 h-4 ml-1" />
                </button>
              </div>
            )}
          </div>
        )}

        {/* STEP 3: LOCATION SELECTION */}
        {currentStep === 3 && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-900">Step 3: Service Location</h2>
                <p className="text-xs text-slate-500">
                  Where should our certified specialist arrive to service your vehicle?
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowAddAddress(!showAddAddress)}
                className="inline-flex items-center px-3 py-1.5 rounded-xl border border-emerald-300 bg-emerald-50 text-emerald-800 text-xs font-bold hover:bg-emerald-100 transition"
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                {showAddAddress ? 'Cancel' : 'New Address'}
              </button>
            </div>

            {/* Add Address Form */}
            {showAddAddress && (
              <form
                onSubmit={handleAddNewAddress}
                className="bg-slate-50 border border-slate-200 rounded-2xl p-5 space-y-4 text-xs animate-in fade-in"
              >
                <h3 className="font-bold text-slate-900 text-sm">Save New Service Address</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Label</label>
                    <select
                      value={newAddressLabel}
                      onChange={(e) => setNewAddressLabel(e.target.value)}
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    >
                      <option value="Home">Home</option>
                      <option value="Office">Office</option>
                      <option value="Garage">Garage / Other</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Area / Locality</label>
                    <input
                      type="text"
                      placeholder="e.g. Indiranagar, HSR Layout"
                      value={newArea}
                      onChange={(e) => setNewArea(e.target.value)}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block font-semibold text-slate-700 mb-1">
                      Street Address & Flat / House No.
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. #42, 12th Main Road, Near Metro Station"
                      value={newAddressLine}
                      onChange={(e) => setNewAddressLine(e.target.value)}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">City</label>
                    <input
                      type="text"
                      value={newCity}
                      onChange={(e) => setNewCity(e.target.value)}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">State</label>
                    <input
                      type="text"
                      value={newState}
                      onChange={(e) => setNewState(e.target.value)}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl"
                    />
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Postal Code</label>
                    <input
                      type="text"
                      placeholder="e.g. 560038"
                      value={newPostalCode}
                      onChange={(e) => setNewPostalCode(e.target.value)}
                      required
                      className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl font-mono"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={createAddressMutation.isPending}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl shadow-xs transition"
                  >
                    {createAddressMutation.isPending ? 'Saving...' : 'Save & Select Location'}
                  </button>
                </div>
              </form>
            )}

            {/* Saved Addresses List */}
            {isLoadingAddresses ? (
              <div className="py-12 flex justify-center">
                <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : myAddresses.length === 0 ? (
              <div className="border-2 border-dashed border-slate-200 rounded-2xl p-8 text-center space-y-3">
                <MapPin className="w-10 h-10 text-slate-300 mx-auto" />
                <h4 className="font-bold text-slate-700">No saved addresses</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Click "New Address" above to enter your service location.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {myAddresses.map((addr) => {
                  const isSelected = selectedAddress?.id === addr.id;

                  return (
                    <div
                      key={addr.id}
                      onClick={() => setSelectedAddress(addr)}
                      className={`p-4 rounded-2xl border-2 transition cursor-pointer flex items-start justify-between ${
                        isSelected
                          ? 'border-emerald-600 bg-emerald-50/40 shadow-xs'
                          : 'border-slate-200 hover:border-slate-300 bg-white'
                      }`}
                    >
                      <div className="flex items-start space-x-3">
                        <div
                          className={`p-2.5 rounded-xl shrink-0 mt-0.5 ${
                            isSelected
                              ? 'bg-emerald-600 text-white'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          <MapPin className="w-5 h-5" />
                        </div>
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="font-bold text-slate-900 text-sm">{addr.label}</span>
                            {addr.is_default && (
                              <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded-md font-semibold">
                                Default
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                            {addr.address_line}, {addr.area}
                          </p>
                          <p className="text-[11px] text-slate-400">
                            {addr.city}, {addr.state} - {addr.postal_code}
                          </p>
                        </div>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ml-2 mt-1 ${
                          isSelected ? 'border-emerald-600 bg-emerald-600' : 'border-slate-300'
                        }`}
                      >
                        {isSelected && <div className="w-2 h-2 rounded-full bg-white" />}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* STEP 4: TIMING & INSTRUCTIONS */}
        {currentStep === 4 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Step 4: Timing & Special Notes</h2>
              <p className="text-xs text-slate-500">
                Choose immediate arrival or reserve an appointment for later
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Immediate Dispatch Card */}
              <div
                onClick={() => setTimingType('immediate')}
                className={`p-5 rounded-2xl border-2 transition cursor-pointer flex flex-col justify-between ${
                  timingType === 'immediate'
                    ? 'border-emerald-600 bg-emerald-50/40 shadow-xs'
                    : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <div
                      className={`p-2 rounded-xl ${
                        timingType === 'immediate'
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      <Clock className="w-5 h-5" />
                    </div>
                    <h4 className="font-bold text-slate-900 text-sm">Immediate Dispatch</h4>
                  </div>
                  <p className="text-xs text-slate-600">
                    Nearest available specialist receives instant dispatch offer. Recommended for
                    urgent repairs and breakdowns.
                  </p>
                </div>
                <div className="mt-4 pt-2 text-[11px] text-emerald-700 font-semibold flex items-center">
                  <span className="w-2 h-2 rounded-full bg-emerald-600 mr-1.5 animate-ping" />
                  Estimated arrival ~30-45 minutes
                </div>
              </div>

              {/* Scheduled Appointment Card */}
              <div
                onClick={() => setTimingType('scheduled')}
                className={`p-5 rounded-2xl border-2 transition cursor-pointer flex flex-col justify-between ${
                  timingType === 'scheduled'
                    ? 'border-emerald-600 bg-emerald-50/40 shadow-xs'
                    : 'border-slate-200 hover:border-slate-300 bg-white'
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <div
                      className={`p-2 rounded-xl ${
                        timingType === 'scheduled'
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      <Calendar className="w-5 h-5" />
                    </div>
                    <h4 className="font-bold text-slate-900 text-sm">Schedule for Later</h4>
                  </div>
                  <p className="text-xs text-slate-600">
                    Book a confirmed calendar window on any upcoming day at your convenience.
                  </p>
                </div>
                <div className="mt-4 pt-2 text-[11px] text-slate-500">
                  Select preferred date & time window below
                </div>
              </div>
            </div>

            {/* Scheduled Date/Time Inputs */}
            {timingType === 'scheduled' && (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 grid grid-cols-1 sm:grid-cols-2 gap-4 animate-in fade-in">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Service Date
                  </label>
                  <input
                    type="date"
                    min={new Date().toISOString().split('T')[0]}
                    value={scheduledDate}
                    onChange={(e) => setScheduledDate(e.target.value)}
                    required
                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Preferred Time Window
                  </label>
                  <select
                    value={scheduledTime}
                    onChange={(e) => setScheduledTime(e.target.value)}
                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-xs"
                  >
                    <option value="09:00">Morning (09:00 AM - 11:00 AM)</option>
                    <option value="12:00">Midday (12:00 PM - 02:00 PM)</option>
                    <option value="15:00">Afternoon (03:00 PM - 05:00 PM)</option>
                    <option value="17:00">Evening (05:00 PM - 07:00 PM)</option>
                  </select>
                </div>
              </div>
            )}

            {/* Customer Special Instructions */}
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Vehicle Symptoms / Instructions for Mechanic (Optional)
              </label>
              <textarea
                rows={3}
                placeholder="e.g. Unusual rattling noise from front suspension, please carry engine oil for 125cc."
                value={customerNotes}
                onChange={(e) => setCustomerNotes(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-xs focus:ring-2 focus:ring-emerald-600 focus:outline-none"
              />
            </div>
          </div>
        )}

        {/* STEP 5: REVIEW & CONFIRM */}
        {currentStep === 5 && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Step 5: Review & Confirm Booking</h2>
              <p className="text-xs text-slate-500">
                Please verify your vehicle, services, location, and estimated cost
              </p>
            </div>

            {submissionError && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-4 rounded-xl flex items-start space-x-2">
                <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                <span>{submissionError}</span>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Vehicle & Location Review Card */}
              <div className="space-y-4">
                <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-4 space-y-2">
                  <div className="flex items-center space-x-2 text-slate-900 font-bold text-xs uppercase tracking-wider">
                    <Car className="w-4 h-4 text-emerald-600" />
                    <span>Target Vehicle</span>
                  </div>
                  <div className="text-xs text-slate-800">
                    <span className="font-bold text-sm block">
                      {selectedVehicle?.vehicle_brands?.name} {selectedVehicle?.vehicle_models?.name}
                    </span>
                    <span className="text-slate-500 font-mono">
                      {selectedVehicle?.registration_number} • {selectedVehicle?.fuel_type} (
                      {selectedVehicle?.manufacture_year})
                    </span>
                  </div>
                </div>

                <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-4 space-y-2">
                  <div className="flex items-center space-x-2 text-slate-900 font-bold text-xs uppercase tracking-wider">
                    <MapPin className="w-4 h-4 text-emerald-600" />
                    <span>Doorstep Address</span>
                  </div>
                  <div className="text-xs text-slate-800">
                    <span className="font-bold block">{selectedAddress?.label}</span>
                    <p className="text-slate-600 mt-0.5">
                      {selectedAddress?.address_line}, {selectedAddress?.area}
                      <br />
                      {selectedAddress?.city}, {selectedAddress?.state} -{' '}
                      {selectedAddress?.postal_code}
                    </p>
                  </div>
                </div>

                <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-4 space-y-2">
                  <div className="flex items-center space-x-2 text-slate-900 font-bold text-xs uppercase tracking-wider">
                    <Clock className="w-4 h-4 text-emerald-600" />
                    <span>Appointment Timing</span>
                  </div>
                  <div className="text-xs text-slate-800">
                    {timingType === 'immediate' ? (
                      <span className="inline-flex items-center text-emerald-700 font-bold">
                        <span className="w-2 h-2 rounded-full bg-emerald-600 mr-1.5 animate-ping" />
                        Immediate Doorstep Dispatch
                      </span>
                    ) : (
                      <span>
                        Scheduled for{' '}
                        <strong>
                          {new Date(`${scheduledDate}T${scheduledTime}:00`).toLocaleString(
                            undefined,
                            {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            }
                          )}
                        </strong>
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Service Items & Authoritative Pricing Estimate */}
              <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-5 space-y-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center space-x-2 text-slate-900 font-bold text-xs uppercase tracking-wider border-b border-slate-200/80 pb-2.5">
                    <Receipt className="w-4 h-4 text-emerald-600" />
                    <span>Selected Services ({selectedServicesList.length})</span>
                  </div>

                  <div className="divide-y divide-slate-200/60 my-2">
                    {selectedServicesList.map((svc) => (
                      <div
                        key={svc.id}
                        className="py-2.5 flex items-center justify-between text-xs"
                      >
                        <div>
                          <p className="font-bold text-slate-900">{svc.name}</p>
                          <span className="text-[11px] text-slate-500">
                            ~{svc.estimated_duration_minutes} mins
                          </span>
                        </div>
                        <span className="font-bold text-slate-900">
                          ₹{getServicePrice(svc).toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-200/80 space-y-2 text-xs text-slate-600">
                  <div className="flex justify-between">
                    <span>Labor & Parts Subtotal</span>
                    <span>₹{estimatedSubtotal.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>GST (18%)</span>
                    <span>₹{estimatedGst.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-base font-black text-slate-900 pt-2 border-t border-slate-200">
                    <span>Estimated Total</span>
                    <span className="text-emerald-700">₹{estimatedTotal.toFixed(2)}</span>
                  </div>
                  <p className="text-[10px] text-slate-400 italic pt-1">
                    * The platform authoritatively verifies catalog pricing upon order placement.
                    Payment is collected securely via sandbox upon service completion.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Wizard Footer Controls */}
        <div className="mt-8 pt-6 border-t border-slate-100 flex items-center justify-between">
          {currentStep > 1 ? (
            <button
              type="button"
              onClick={() => setCurrentStep((prev) => Math.max(1, prev - 1))}
              disabled={createBookingMutation.isPending}
              className="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition flex items-center"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
              Back
            </button>
          ) : (
            <div />
          )}

          {currentStep < 5 ? (
            <button
              type="button"
              onClick={() => setCurrentStep((prev) => Math.min(5, prev + 1))}
              disabled={!isStepValid(currentStep)}
              className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 text-white rounded-xl text-xs font-bold shadow-sm transition flex items-center"
            >
              <span>Continue</span>
              <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleConfirmBooking}
              disabled={createBookingMutation.isPending || !isStepValid(5)}
              className="px-8 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition flex items-center space-x-2"
            >
              {createBookingMutation.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Confirming Booking...</span>
                </>
              ) : (
                <>
                  <Shield className="w-4 h-4" />
                  <span>Confirm & Dispatch Service</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
