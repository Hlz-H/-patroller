import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface StatusBadgeProps {
  status: 'online' | 'offline' | 'paused';
  size?: 'small' | 'medium';
}

const colors: Record<string, string> = {
  online: '#22C55E',
  offline: '#EF4444',
  paused: '#F59E0B',
};

const labels: Record<string, string> = {
  online: 'Online',
  offline: 'Offline',
  paused: 'Paused',
};

export default function StatusBadge({ status, size = 'medium' }: StatusBadgeProps) {
  const isSmall = size === 'small';
  return (
    <View style={[styles.container, isSmall && styles.smallContainer]}>
      <View
        style={[
          styles.dot,
          { backgroundColor: colors[status] || '#8B949E' },
          isSmall && styles.smallDot,
        ]}
      />
      <Text
        style={[
          styles.label,
          { color: colors[status] || '#8B949E' },
          isSmall && styles.smallLabel,
        ]}
      >
        {labels[status] || status}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  smallContainer: {
    gap: 4,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  smallDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
  },
  label: {
    fontSize: 13,
    fontWeight: '500',
  },
  smallLabel: {
    fontSize: 11,
  },
});
