import { useEffect, useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useLocalSearchParams, Stack, useRouter } from 'expo-router';
import { useDeviceStore } from '../../src/stores/deviceStore';
import { useAlertStore } from '../../src/stores/alertStore';
import { useAppStore } from '../../src/stores/appStore';
import * as api from '../../src/services/api';
import StatusBadge from '../../src/components/StatusBadge';
import MetricCard from '../../src/components/MetricCard';
import AlertRow from '../../src/components/AlertRow';

export default function DeviceDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const deviceId = id as string;

  const device = useDeviceStore((s) => s.getDevice(deviceId));
  const metrics = useDeviceStore((s) => s.metricsMap[deviceId]);
  const fetchDevices = useDeviceStore((s) => s.fetchDevices);
  const alerts = useAlertStore((s) => s.alerts);
  const fetchAlerts = useAlertStore((s) => s.fetchAlerts);
  const loading = useAlertStore((s) => s.loading);
  const backendUrl = useAppStore((s) => s.config.backendUrl);

  const deviceAlerts = alerts.filter((a) => a.deviceId === deviceId).slice(0, 10);

  const fetchData = useCallback(() => {
    fetchDevices();
    fetchAlerts({ deviceId });
  }, [deviceId]);

  useEffect(() => {
    if (backendUrl) fetchData();
  }, [id, backendUrl]);

  const handleCommand = (action: string) => {
    Alert.alert(
      'Confirm Command',
      `Send "${action}" to device "${device?.name}"?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Send',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.relay.sendCommand(deviceId, action);
              Alert.alert('Sent', `Command "${action}" dispatched`);
            } catch (err) {
              Alert.alert('Error', 'Failed to send command');
            }
          },
        },
      ]
    );
  };

  if (!device) {
    return (
      <View style={styles.container}>
        <Stack.Screen options={{ title: 'Device Not Found' }} />
        <Text style={styles.notFound}>Device not found</Text>
      </View>
    );
  }

  const cpuPercent = metrics?.cpu.percent;
  const memPercent = metrics?.memory.percent;
  const diskPercent = metrics?.disk.percent;

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
      <Stack.Screen
        options={{
          title: device.name,
          headerStyle: { backgroundColor: '#0D1117' },
          headerTintColor: '#E6EDF3',
          headerShadowVisible: false,
        }}
      />

      {/* Device Info */}
      <View style={styles.infoCard}>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Status</Text>
          <StatusBadge status={device.status} />
        </View>
        {device.localIp && (
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>IP</Text>
            <Text style={styles.infoValue}>{device.localIp}</Text>
          </View>
        )}
        {device.version && (
          <View style={styles.infoRow}>
            <Text style={styles.infoLabel}>Version</Text>
            <Text style={styles.infoValue}>{device.version}</Text>
          </View>
        )}
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Last Seen</Text>
          <Text style={styles.infoValue}>
            {new Date(device.lastSeen).toLocaleString()}
          </Text>
        </View>
      </View>

      {/* Metrics */}
      <Text style={styles.sectionTitle}>System Metrics</Text>
      {metrics ? (
        <View style={styles.metricsGrid}>
          <MetricCard
            title="CPU"
            value={`${cpuPercent?.toFixed(1) ?? '--'}%`}
            color={cpuPercent && cpuPercent > 80 ? '#EF4444' : '#58A6FF'}
            icon="⚡"
          />
          <MetricCard
            title="Memory"
            value={`${memPercent?.toFixed(1) ?? '--'}%`}
            color={memPercent && memPercent > 80 ? '#EF4444' : '#22C55E'}
            icon="🧠"
          />
          <MetricCard
            title="Disk"
            value={`${diskPercent?.toFixed(1) ?? '--'}%`}
            color={diskPercent && diskPercent > 90 ? '#EF4444' : '#F59E0B'}
            icon="💾"
          />
          <MetricCard
            title="Network"
            value={
              metrics
                ? `${(metrics.network.bytesRecv / 1024 / 1024).toFixed(1)} MB`
                : '--'
            }
            color="#8B5CF6"
            icon="📡"
          />
        </View>
      ) : (
        <View style={styles.noMetrics}>
          <Text style={styles.noMetricsText}>No metrics available</Text>
        </View>
      )}

      {/* Quick Actions */}
      <Text style={styles.sectionTitle}>Quick Actions</Text>
      <View style={styles.actionRow}>
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => handleCommand('scan')}
        >
          <Text style={styles.actionIcon}>🔍</Text>
          <Text style={styles.actionText}>Scan</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => handleCommand('update')}
        >
          <Text style={styles.actionIcon}>🔄</Text>
          <Text style={styles.actionText}>Update</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.actionBtn, styles.actionDanger]}
          onPress={() => handleCommand('lockdown')}
        >
          <Text style={styles.actionIcon}>🔒</Text>
          <Text style={[styles.actionText, styles.actionDangerText]}>
            Lockdown
          </Text>
        </TouchableOpacity>
      </View>

      {/* Recent Alerts for this device */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Recent Alerts</Text>
        {deviceAlerts.length > 0 && (
          <Text
            style={styles.viewAll}
            onPress={() =>
              router.push({
                pathname: '/(tabs)/alerts',
                params: { deviceId },
              })
            }
          >
            View all →
          </Text>
        )}
      </View>

      {deviceAlerts.length === 0 ? (
        <View style={styles.emptyAlerts}>
          <Text style={styles.emptyText}>No alerts for this device</Text>
        </View>
      ) : (
        deviceAlerts.map((alert) => (
          <AlertRow
            key={alert.id}
            alert={alert}
            onPress={() => router.push(`/alerts/${alert.id}`)}
          />
        ))
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
    paddingBottom: 40,
  },
  notFound: {
    color: '#EF4444',
    fontSize: 16,
    textAlign: 'center',
    marginTop: 60,
  },
  infoCard: {
    backgroundColor: '#161B22',
    borderRadius: 12,
    margin: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#30363D',
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
  },
  infoLabel: {
    color: '#8B949E',
    fontSize: 14,
  },
  infoValue: {
    color: '#E6EDF3',
    fontSize: 14,
    fontWeight: '500',
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
    marginTop: 8,
  },
  viewAll: {
    color: '#58A6FF',
    fontSize: 13,
    fontWeight: '500',
    marginRight: 16,
  },
  metricsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginHorizontal: 16,
    marginBottom: 12,
  },
  noMetrics: {
    backgroundColor: '#161B22',
    borderRadius: 10,
    padding: 24,
    marginHorizontal: 16,
    alignItems: 'center',
  },
  noMetricsText: {
    color: '#8B949E',
    fontSize: 14,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    marginHorizontal: 16,
    marginBottom: 12,
  },
  actionBtn: {
    flex: 1,
    backgroundColor: '#161B22',
    borderRadius: 10,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#30363D',
  },
  actionDanger: {
    borderColor: '#EF444444',
  },
  actionIcon: {
    fontSize: 22,
    marginBottom: 4,
  },
  actionText: {
    color: '#E6EDF3',
    fontSize: 12,
    fontWeight: '600',
  },
  actionDangerText: {
    color: '#EF4444',
  },
  emptyAlerts: {
    backgroundColor: '#161B22',
    borderRadius: 10,
    padding: 24,
    marginHorizontal: 16,
    alignItems: 'center',
  },
  emptyText: {
    color: '#8B949E',
    fontSize: 14,
  },
});
