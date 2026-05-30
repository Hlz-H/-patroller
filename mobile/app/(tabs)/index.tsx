import { useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useDeviceStore } from '../../src/stores/deviceStore';
import { useAlertStore } from '../../src/stores/alertStore';
import { useAppStore } from '../../src/stores/appStore';
import MetricCard from '../../src/components/MetricCard';
import AlertRow from '../../src/components/AlertRow';
import EmptyState from '../../src/components/EmptyState';

export default function DashboardScreen() {
  const router = useRouter();
  const devices = useDeviceStore((s) => s.devices);
  const fetchDevices = useDeviceStore((s) => s.fetchDevices);
  const alerts = useAlertStore((s) => s.alerts);
  const fetchAlerts = useAlertStore((s) => s.fetchAlerts);
  const loading = useAlertStore((s) => s.loading);
  const isConnected = useAppStore((s) => s.isConnected);
  const testAndConnect = useAppStore((s) => s.testAndConnect);
  const backendUrl = useAppStore((s) => s.config.backendUrl);

  const fetchData = useCallback(async () => {
    if (!backendUrl) return;
    await Promise.all([fetchDevices(), fetchAlerts({ limit: 10 })]);
  }, [backendUrl]);

  useEffect(() => {
    if (backendUrl) {
      testAndConnect().then(() => fetchData());
    }
  }, [backendUrl]);

  const onlineCount = devices.filter((d) => d.status === 'online').length;
  const offlineCount = devices.filter((d) => d.status === 'offline').length;
  const unacknowledged = alerts.filter((a) => !a.acknowledged).length;
  const critical = alerts.filter((a) => a.severity === 'critical').length;
  const recentAlerts = alerts.slice(0, 5);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={loading}
          onRefresh={fetchData}
          tintColor="#58A6FF"
        />
      }
    >
      {/* Connection Status */}
      {!isConnected && backendUrl ? (
        <View style={styles.disconnectedBanner}>
          <Text style={styles.disconnectedText}>
            ⚠️ Disconnected — check server configuration
          </Text>
        </View>
      ) : null}

      {!backendUrl ? (
        <EmptyState
          icon="🔌"
          title="No server configured"
          subtitle="Go to Settings to enter your Backend server URL"
        />
      ) : (
        <>
          {/* Status Summary */}
          <Text style={styles.sectionTitle}>Overview</Text>
          <View style={styles.metricsRow}>
            <MetricCard
              title="Devices"
              value={String(devices.length)}
              subtitle={`${onlineCount} online, ${offlineCount} offline`}
              color="#58A6FF"
              icon="💻"
            />
            <MetricCard
              title="Alerts"
              value={String(alerts.length)}
              subtitle={`${unacknowledged} unacknowledged`}
              color={unacknowledged > 0 ? '#F59E0B' : '#22C55E'}
              icon="🔔"
            />
          </View>
          <View style={styles.metricsRow}>
            <MetricCard
              title="Online"
              value={String(onlineCount)}
              subtitle={`${devices.length > 0 ? Math.round((onlineCount / devices.length) * 100) : 0}% of total`}
              color="#22C55E"
              icon="🟢"
            />
            <MetricCard
              title="Critical"
              value={String(critical)}
              subtitle="Requires immediate attention"
              color={critical > 0 ? '#EF4444' : '#6B7280'}
              icon="🚨"
            />
          </View>

          {/* Recent Alerts */}
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recent Alerts</Text>
            {alerts.length > 5 && (
              <Text
                style={styles.viewAll}
                onPress={() => router.push('/(tabs)/alerts')}
              >
                View all →
              </Text>
            )}
          </View>

          {recentAlerts.length === 0 ? (
            <View style={styles.emptyAlerts}>
              <Text style={styles.emptyText}>No recent alerts</Text>
            </View>
          ) : (
            recentAlerts.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                onPress={() => router.push(`/alerts/${alert.id}`)}
              />
            ))
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0D1117',
  },
  content: {
    paddingVertical: 16,
    paddingBottom: 32,
  },
  disconnectedBanner: {
    backgroundColor: '#EF444422',
    borderWidth: 1,
    borderColor: '#EF4444',
    borderRadius: 8,
    padding: 12,
    marginHorizontal: 16,
    marginBottom: 12,
  },
  disconnectedText: {
    color: '#FCA5A5',
    fontSize: 13,
    textAlign: 'center',
  },
  sectionTitle: {
    color: '#E6EDF3',
    fontSize: 17,
    fontWeight: '600',
    marginHorizontal: 16,
    marginBottom: 12,
    marginTop: 8,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 16,
  },
  viewAll: {
    color: '#58A6FF',
    fontSize: 13,
    fontWeight: '500',
    marginRight: 16,
  },
  metricsRow: {
    flexDirection: 'row',
    gap: 10,
    marginHorizontal: 16,
    marginBottom: 10,
  },
  emptyAlerts: {
    backgroundColor: '#161B22',
    borderRadius: 10,
    padding: 32,
    marginHorizontal: 16,
    alignItems: 'center',
  },
  emptyText: {
    color: '#8B949E',
    fontSize: 14,
  },
});
