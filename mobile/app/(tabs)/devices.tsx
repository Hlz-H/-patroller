import { useEffect, useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useDeviceStore } from '../../src/stores/deviceStore';
import { Device } from '../../src/types';
import DeviceCard from '../../src/components/DeviceCard';
import EmptyState from '../../src/components/EmptyState';

type FilterMode = 'all' | 'online' | 'offline';

export default function DevicesScreen() {
  const router = useRouter();
  const devices = useDeviceStore((s) => s.devices);
  const fetchDevices = useDeviceStore((s) => s.fetchDevices);
  const loading = useDeviceStore((s) => s.loading);
  const [filter, setFilter] = useState<FilterMode>('all');

  useEffect(() => {
    fetchDevices();
  }, []);

  const filteredDevices =
    filter === 'all'
      ? devices
      : devices.filter((d) => d.status === filter);

  const handleDevicePress = (device: Device) => {
    router.push(`/devices/${device.id}`);
  };

  const counts = {
    all: devices.length,
    online: devices.filter((d) => d.status === 'online').length,
    offline: devices.filter((d) => d.status === 'offline').length,
  };

  const renderFilterButton = (mode: FilterMode, label: string, count: number) => (
    <TouchableOpacity
      key={mode}
      style={[styles.filterBtn, filter === mode && styles.filterBtnActive]}
      onPress={() => setFilter(mode)}
    >
      <Text style={[styles.filterText, filter === mode && styles.filterTextActive]}>
        {label} ({count})
      </Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.filterRow}>
        {renderFilterButton('all', 'All', counts.all)}
        {renderFilterButton('online', 'Online', counts.online)}
        {renderFilterButton('offline', 'Offline', counts.offline)}
      </View>

      <FlatList
        data={filteredDevices}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <DeviceCard device={item} onPress={handleDevicePress} />
        )}
        contentContainerStyle={filteredDevices.length === 0 ? styles.emptyContainer : styles.list}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={fetchDevices}
            tintColor="#58A6FF"
          />
        }
        ListEmptyComponent={
          <EmptyState
            icon="💻"
            title="No devices found"
            subtitle={
              filter !== 'all'
                ? `No ${filter} devices available`
                : 'Connect an Agent to get started'
            }
          />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0D1117',
  },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
  },
  filterBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#161B22',
    borderWidth: 1,
    borderColor: '#30363D',
  },
  filterBtnActive: {
    backgroundColor: '#1F6FEB22',
    borderColor: '#58A6FF',
  },
  filterText: {
    color: '#8B949E',
    fontSize: 13,
    fontWeight: '500',
  },
  filterTextActive: {
    color: '#58A6FF',
  },
  list: {
    paddingBottom: 20,
  },
  emptyContainer: {
    flex: 1,
  },
});
