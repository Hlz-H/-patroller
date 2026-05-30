import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Device } from '../types';
import StatusBadge from './StatusBadge';

interface DeviceCardProps {
  device: Device;
  onPress: (device: Device) => void;
}

export default function DeviceCard({ device, onPress }: DeviceCardProps) {
  const lastSeen = new Date(device.lastSeen).toLocaleString();
  const isOnline = device.status === 'online';

  return (
    <TouchableOpacity
      style={[styles.card, isOnline ? styles.online : styles.offline]}
      onPress={() => onPress(device)}
      activeOpacity={0.7}
    >
      <View style={styles.header}>
        <Text style={styles.name}>{device.name}</Text>
        <StatusBadge status={device.status} size="small" />
      </View>

      <View style={styles.details}>
        {device.localIp && (
          <Text style={styles.detail}>
            <Text style={styles.label}>IP: </Text>
            {device.localIp}
          </Text>
        )}
        {device.version && (
          <Text style={styles.detail}>
            <Text style={styles.label}>v</Text>
            {device.version}
          </Text>
        )}
        <Text style={styles.detail}>
          <Text style={styles.label}>Last seen: </Text>
          {lastSeen}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#161B22',
    borderRadius: 12,
    padding: 16,
    marginHorizontal: 16,
    marginVertical: 4,
    borderWidth: 1,
  },
  online: {
    borderColor: '#22C55E33',
  },
  offline: {
    borderColor: '#30363D',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  name: {
    color: '#E6EDF3',
    fontSize: 16,
    fontWeight: '600',
  },
  details: {
    gap: 4,
  },
  detail: {
    color: '#8B949E',
    fontSize: 13,
  },
  label: {
    color: '#6E7681',
    fontWeight: '500',
  },
});
