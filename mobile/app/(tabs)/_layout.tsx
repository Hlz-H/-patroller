import { Tabs } from 'expo-router';
import { Text, View, StyleSheet } from 'react-native';
import { useAlertStore } from '../../src/stores/alertStore';
import { useAppStore } from '../../src/stores/appStore';

function TabIcon({ name, focused }: { name: string; focused: boolean }) {
  const iconMap: Record<string, string> = {
    dashboard: '📊',
    devices: '💻',
    alerts: '🔔',
    settings: '⚙️',
  };
  return (
    <Text style={{ fontSize: 22, opacity: focused ? 1 : 0.5 }}>
      {iconMap[name] || '•'}
    </Text>
  );
}

function AlertsBadge() {
  const count = useAlertStore((s) => s.getUnacknowledgedCount());
  if (count <= 0) return null;
  return (
    <View style={styles.badge}>
      <Text style={styles.badgeText}>{count > 99 ? '99+' : count}</Text>
    </View>
  );
}

function ConnectionDot() {
  const isConnected = useAppStore((s) => s.isConnected);
  return (
    <View
      style={[
        styles.connectionDot,
        { backgroundColor: isConnected ? '#22C55E' : '#EF4444' },
      ]}
    />
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: '#0D1117' },
        headerTintColor: '#E6EDF3',
        tabBarStyle: {
          backgroundColor: '#161B22',
          borderTopColor: '#30363D',
          borderTopWidth: 1,
          paddingBottom: 6,
          paddingTop: 6,
          height: 60,
        },
        tabBarActiveTintColor: '#58A6FF',
        tabBarInactiveTintColor: '#8B949E',
        tabBarLabelStyle: { fontSize: 11, fontWeight: '500' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Dashboard',
          tabBarIcon: ({ focused }) => <TabIcon name="dashboard" focused={focused} />,
          headerTitle: () => (
            <View style={styles.headerTitle}>
              <Text style={styles.headerText}>巡查者</Text>
              <ConnectionDot />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="devices"
        options={{
          title: 'Devices',
          tabBarIcon: ({ focused }) => <TabIcon name="devices" focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="alerts"
        options={{
          title: 'Alerts',
          tabBarIcon: ({ focused }) => (
            <View>
              <TabIcon name="alerts" focused={focused} />
              <AlertsBadge />
            </View>
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ focused }) => <TabIcon name="settings" focused={focused} />,
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  headerTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerText: {
    color: '#E6EDF3',
    fontSize: 18,
    fontWeight: '600',
  },
  connectionDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  badge: {
    position: 'absolute',
    top: -4,
    right: -8,
    backgroundColor: '#EF4444',
    borderRadius: 10,
    minWidth: 18,
    height: 18,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '700',
  },
});
