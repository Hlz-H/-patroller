import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Alert } from '../types';

interface AlertRowProps {
  alert: Alert;
  onPress: (alert: Alert) => void;
}

const severityColors: Record<string, string> = {
  critical: '#EF4444',
  high: '#F59E0B',
  medium: '#3B82F6',
  low: '#6B7280',
  info: '#22C55E',
};

const severityLabels: Record<string, string> = {
  critical: 'CRIT',
  high: 'HIGH',
  medium: 'MED',
  low: 'LOW',
  info: 'INFO',
};

export default function AlertRow({ alert, onPress }: AlertRowProps) {
  const severityColor = severityColors[alert.severity] || '#6B7280';
  const severityLabel = severityLabels[alert.severity] || alert.severity.toUpperCase();
  const time = new Date(alert.timestamp).toLocaleTimeString();
  const aggregated = alert.count && alert.count > 1;

  return (
    <TouchableOpacity
      style={[styles.row, !alert.acknowledged && styles.unacknowledged]}
      onPress={() => onPress(alert)}
      activeOpacity={0.7}
    >
      <View style={[styles.severityBar, { backgroundColor: severityColor }]} />

      <View style={styles.content}>
        <View style={styles.header}>
          <View style={styles.severityTag}>
            <Text style={[styles.severityText, { color: severityColor }]}>
              {severityLabel}
            </Text>
          </View>
          <Text style={styles.time}>{time}</Text>
        </View>

        <Text style={styles.message} numberOfLines={2}>
          {alert.message}
        </Text>

        <View style={styles.footer}>
          <Text style={styles.type}>{alert.type}</Text>
          {aggregated && (
            <View style={styles.countBadge}>
              <Text style={styles.countText}>×{alert.count}</Text>
            </View>
          )}
          {!alert.acknowledged && <View style={styles.unreadDot} />}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    backgroundColor: '#161B22',
    borderRadius: 10,
    marginHorizontal: 16,
    marginVertical: 3,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#30363D',
  },
  unacknowledged: {
    borderColor: '#58A6FF44',
  },
  severityBar: {
    width: 4,
  },
  content: {
    flex: 1,
    padding: 12,
    gap: 6,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  severityTag: {
    backgroundColor: '#0D1117',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  severityText: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
  },
  time: {
    color: '#6E7681',
    fontSize: 11,
  },
  message: {
    color: '#E6EDF3',
    fontSize: 14,
    lineHeight: 19,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  type: {
    color: '#8B949E',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  countBadge: {
    backgroundColor: '#30363D',
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  countText: {
    color: '#F59E0B',
    fontSize: 10,
    fontWeight: '600',
  },
  unreadDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: '#58A6FF',
    marginLeft: 'auto',
  },
});
