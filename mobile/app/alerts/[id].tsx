import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { useLocalSearchParams, Stack } from 'expo-router';
import { useAlertStore } from '../../src/stores/alertStore';

export default function AlertDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const alertId = id as string;
  const alerts = useAlertStore((s) => s.alerts);
  const acknowledgeAlert = useAlertStore((s) => s.acknowledgeAlert);
  const alert = alerts.find((a) => a.id === alertId);

  if (!alert) {
    return (
      <View style={styles.container}>
        <Stack.Screen options={{ title: 'Alert Not Found' }} />
        <Text style={styles.notFound}>Alert not found</Text>
      </View>
    );
  }

  const time = new Date(alert.timestamp).toLocaleString();
  const severityColors: Record<string, string> = {
    critical: '#EF4444',
    high: '#F59E0B',
    medium: '#3B82F6',
    low: '#6B7280',
    info: '#22C55E',
  };
  const severityColor = severityColors[alert.severity] || '#6B7280';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Stack.Screen
        options={{
          title: `${alert.severity.toUpperCase()} Alert`,
          headerStyle: { backgroundColor: '#0D1117' },
          headerTintColor: '#E6EDF3',
          headerShadowVisible: false,
        }}
      />

      {/* Severity Banner */}
      <View style={[styles.severityBanner, { backgroundColor: severityColor + '22', borderColor: severityColor }]}>
        <View style={[styles.severityDot, { backgroundColor: severityColor }]} />
        <Text style={[styles.severityLabel, { color: severityColor }]}>
          {alert.severity.toUpperCase()}
        </Text>
        {alert.count && alert.count > 1 && (
          <View style={styles.countBadge}>
            <Text style={styles.countText}>×{alert.count} occurrences</Text>
          </View>
        )}
      </View>

      {/* Message */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>Message</Text>
        <Text style={styles.message}>{alert.message}</Text>
      </View>

      {/* Details */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>Details</Text>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Type</Text>
          <Text style={styles.detailValue}>{alert.type}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Device ID</Text>
          <Text style={styles.detailValue}>{alert.deviceId}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Timestamp</Text>
          <Text style={styles.detailValue}>{time}</Text>
        </View>
        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Status</Text>
          <Text style={[styles.detailValue, alert.acknowledged && styles.acknowledged]}>
            {alert.acknowledged ? '✓ Acknowledged' : 'Unacknowledged'}
          </Text>
        </View>
        {alert.groupKey && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Group Key</Text>
            <Text style={styles.detailValue}>{alert.groupKey}</Text>
          </View>
        )}
      </View>

      {/* Details JSON (if present) */}
      {alert.details != null && (
        <View style={styles.section}>
          <Text style={styles.sectionLabel}>Raw Details</Text>
          <View style={styles.jsonBox}>
            <Text style={styles.jsonText}>
              {JSON.stringify(alert.details, null, 2)}
            </Text>
          </View>
        </View>
      )}

      {/* Acknowledge Button */}
      {!alert.acknowledged && (
        <TouchableOpacity
          style={styles.ackBtn}
          onPress={() => acknowledgeAlert(alert.id)}
        >
          <Text style={styles.ackBtnText}>✓ Acknowledge</Text>
        </TouchableOpacity>
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
  severityBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    margin: 16,
    padding: 14,
    borderRadius: 10,
    borderWidth: 1,
  },
  severityDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  severityLabel: {
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 1,
  },
  countBadge: {
    backgroundColor: '#30363D',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginLeft: 'auto',
  },
  countText: {
    color: '#F59E0B',
    fontSize: 12,
    fontWeight: '600',
  },
  section: {
    marginHorizontal: 16,
    marginBottom: 16,
    backgroundColor: '#161B22',
    borderRadius: 10,
    padding: 16,
    borderWidth: 1,
    borderColor: '#30363D',
  },
  sectionLabel: {
    color: '#8B949E',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  message: {
    color: '#E6EDF3',
    fontSize: 16,
    lineHeight: 22,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
  },
  detailLabel: {
    color: '#8B949E',
    fontSize: 13,
  },
  detailValue: {
    color: '#E6EDF3',
    fontSize: 13,
    fontWeight: '500',
  },
  acknowledged: {
    color: '#22C55E',
  },
  jsonBox: {
    backgroundColor: '#0D1117',
    borderRadius: 6,
    padding: 12,
  },
  jsonText: {
    color: '#8B949E',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  ackBtn: {
    marginHorizontal: 16,
    marginTop: 8,
    padding: 16,
    borderRadius: 10,
    backgroundColor: '#22C55E22',
    borderWidth: 1,
    borderColor: '#22C55E',
    alignItems: 'center',
  },
  ackBtnText: {
    color: '#22C55E',
    fontSize: 16,
    fontWeight: '600',
  },
});
