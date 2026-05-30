import { useEffect, useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useRouter, useGlobalSearchParams } from 'expo-router';
import { useAlertStore } from '../../src/stores/alertStore';
import { useAppStore } from '../../src/stores/appStore';
import AlertRow from '../../src/components/AlertRow';
import EmptyState from '../../src/components/EmptyState';

type SeverityFilter = 'all' | 'critical' | 'high' | 'medium' | 'low' | 'info';

const severityOptions: { key: SeverityFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
];

export default function AlertsScreen() {
  const router = useRouter();
  const params = useGlobalSearchParams();
  const alerts = useAlertStore((s) => s.alerts);
  const fetchAlerts = useAlertStore((s) => s.fetchAlerts);
  const loading = useAlertStore((s) => s.loading);
  const acknowledgeAlert = useAlertStore((s) => s.acknowledgeAlert);
  const backendUrl = useAppStore((s) => s.config.backendUrl);
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');

  useEffect(() => {
    if (backendUrl) fetchAlerts();
  }, [backendUrl]);

  const filteredAlerts =
    severityFilter === 'all'
      ? alerts
      : alerts.filter((a) => a.severity === severityFilter);

  const handleAckAll = async () => {
    const unacked = alerts.filter((a) => !a.acknowledged);
    for (const alert of unacked) {
      await acknowledgeAlert(alert.id);
    }
  };

  const renderFilterChip = (opt: { key: SeverityFilter; label: string }) => (
    <TouchableOpacity
      key={opt.key}
      style={[
        styles.chip,
        severityFilter === opt.key && styles.chipActive,
        opt.key === 'critical' && severityFilter === opt.key && styles.chipCritical,
      ]}
      onPress={() => setSeverityFilter(opt.key)}
    >
      <Text
        style={[
          styles.chipText,
          severityFilter === opt.key && styles.chipTextActive,
        ]}
      >
        {opt.label}
      </Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* Filter Row */}
      <View style={styles.filterRow}>
        <FlatList
          horizontal
          data={severityOptions}
          keyExtractor={(item) => item.key}
          renderItem={({ item }) => renderFilterChip(item)}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipList}
        />
        {alerts.filter((a) => !a.acknowledged).length > 0 && (
          <TouchableOpacity style={styles.ackAllBtn} onPress={handleAckAll}>
            <Text style={styles.ackAllText}>Ack All</Text>
          </TouchableOpacity>
        )}
      </View>

      <FlatList
        data={filteredAlerts}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <AlertRow
            alert={item}
            onPress={() => router.push(`/alerts/${item.id}`)}
          />
        )}
        contentContainerStyle={
          filteredAlerts.length === 0 ? styles.emptyContainer : styles.list
        }
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={() => fetchAlerts()}
            tintColor="#58A6FF"
          />
        }
        ListEmptyComponent={
          <EmptyState
            icon="🔔"
            title="No alerts"
            subtitle={
              severityFilter !== 'all'
                ? `No ${severityFilter} severity alerts`
                : 'Your system is running smoothly'
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
    alignItems: 'center',
    paddingVertical: 10,
    paddingRight: 12,
  },
  chipList: {
    paddingHorizontal: 16,
    gap: 6,
  },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#161B22',
    borderWidth: 1,
    borderColor: '#30363D',
  },
  chipActive: {
    backgroundColor: '#1F6FEB22',
    borderColor: '#58A6FF',
  },
  chipCritical: {
    borderColor: '#EF4444',
    backgroundColor: '#EF444422',
  },
  chipText: {
    color: '#8B949E',
    fontSize: 13,
    fontWeight: '500',
  },
  chipTextActive: {
    color: '#58A6FF',
  },
  ackAllBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#22C55E22',
    borderWidth: 1,
    borderColor: '#22C55E',
    marginLeft: 8,
  },
  ackAllText: {
    color: '#22C55E',
    fontSize: 12,
    fontWeight: '600',
  },
  list: {
    paddingBottom: 20,
  },
  emptyContainer: {
    flex: 1,
  },
});
