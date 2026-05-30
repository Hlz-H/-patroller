import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Switch,
  Alert,
} from 'react-native';
import { useAppStore } from '../../src/stores/appStore';
import { requestPermissions, getExpoPushToken } from '../../src/services/notifications';
import { push } from '../../src/services/api';

export default function SettingsScreen() {
  const config = useAppStore((s) => s.config);
  const saveConfig = useAppStore((s) => s.saveConfig);
  const testAndConnect = useAppStore((s) => s.testAndConnect);
  const isConnected = useAppStore((s) => s.isConnected);
  const isConnecting = useAppStore((s) => s.isConnecting);
  const loadConfig = useAppStore((s) => s.loadConfig);

  const [backendUrl, setBackendUrl] = useState(config.backendUrl);
  const [notifications, setNotifications] = useState(config.notificationsEnabled);

  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    setBackendUrl(config.backendUrl);
    setNotifications(config.notificationsEnabled);
  }, [config]);

  const handleSave = async () => {
    await saveConfig({
      backendUrl: backendUrl.replace(/\/+$/, ''), // trim trailing slash
      notificationsEnabled: notifications,
    });
    Alert.alert('Saved', 'Configuration saved successfully');
  };

  const handleTestConnection = async () => {
    await saveConfig({
      backendUrl: backendUrl.replace(/\/+$/, ''),
      notificationsEnabled: notifications,
    });
    const ok = await testAndConnect();
    if (ok) {
      Alert.alert('Connected', 'Successfully connected to Backend');
    } else {
      Alert.alert('Connection Failed', 'Could not reach the server. Check the URL.');
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Connection Status */}
      <View style={styles.statusCard}>
        <View
          style={[
            styles.statusDot,
            { backgroundColor: isConnected ? '#22C55E' : '#EF4444' },
          ]}
        />
        <View>
          <Text style={styles.statusLabel}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </Text>
          <Text style={styles.statusUrl}>{config.backendUrl}</Text>
        </View>
      </View>

      {/* Server Configuration */}
      <Text style={styles.sectionTitle}>Server Configuration</Text>
      <View style={styles.card}>
        <Text style={styles.inputLabel}>Backend URL</Text>
        <TextInput
          style={styles.input}
          value={backendUrl}
          onChangeText={setBackendUrl}
          placeholder="http://192.168.1.100:3099"
          placeholderTextColor="#484F58"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <Text style={styles.hint}>
          Enter the URL of your Patroller Backend server (e.g., Tailscale IP)
        </Text>

        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>Push Notifications</Text>
          <Switch
            value={notifications}
            onValueChange={async (val) => {
              if (val) {
                const { granted, error } = await requestPermissions();
                if (granted) {
                  setNotifications(true);
                  // Register Expo push token with backend
                  const token = await getExpoPushToken();
                  if (token) {
                    await push.registerToken(token);
                    // Save token in config so it persists
                    saveConfig({
                      backendUrl: backendUrl.replace(/\/+$/, ''),
                      notificationsEnabled: true,
                      pushToken: token,
                    });
                  }
                } else {
                  Alert.alert(
                    'Permission Denied',
                    error || 'Notification permission was not granted. Enable it in system settings.'
                  );
                }
              } else {
                setNotifications(false);
              }
            }}
            trackColor={{ false: '#30363D', true: '#1F6FEB' }}
            thumbColor={notifications ? '#58A6FF' : '#8B949E'}
          />
        </View>
      </View>

      {/* Action Buttons */}
      <TouchableOpacity
        style={[styles.btn, styles.btnPrimary]}
        onPress={handleSave}
      >
        <Text style={styles.btnPrimaryText}>Save Configuration</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.btn, styles.btnSecondary]}
        onPress={handleTestConnection}
        disabled={isConnecting}
      >
        <Text style={styles.btnSecondaryText}>
          {isConnecting ? 'Connecting...' : 'Test Connection'}
        </Text>
      </TouchableOpacity>

      {/* About */}
      <Text style={styles.sectionTitle}>About</Text>
      <View style={styles.card}>
        <View style={styles.aboutRow}>
          <Text style={styles.aboutLabel}>App</Text>
          <Text style={styles.aboutValue}>巡查者 Patroller</Text>
        </View>
        <View style={styles.aboutRow}>
          <Text style={styles.aboutLabel}>Version</Text>
          <Text style={styles.aboutValue}>1.0.0</Text>
        </View>
        <View style={styles.aboutRow}>
          <Text style={styles.aboutLabel}>Platform</Text>
          <Text style={styles.aboutValue}>React Native (Expo)</Text>
        </View>
      </View>
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
    paddingBottom: 40,
  },
  statusCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#161B22',
    borderRadius: 12,
    margin: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#30363D',
  },
  statusDot: {
    width: 14,
    height: 14,
    borderRadius: 7,
  },
  statusLabel: {
    color: '#E6EDF3',
    fontSize: 16,
    fontWeight: '600',
  },
  statusUrl: {
    color: '#8B949E',
    fontSize: 13,
    marginTop: 2,
  },
  sectionTitle: {
    color: '#E6EDF3',
    fontSize: 15,
    fontWeight: '600',
    marginHorizontal: 16,
    marginBottom: 10,
    marginTop: 8,
  },
  card: {
    backgroundColor: '#161B22',
    borderRadius: 12,
    marginHorizontal: 16,
    marginBottom: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#30363D',
  },
  inputLabel: {
    color: '#E6EDF3',
    fontSize: 13,
    fontWeight: '500',
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#0D1117',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    color: '#E6EDF3',
    fontSize: 15,
    padding: 12,
    fontFamily: 'monospace',
  },
  hint: {
    color: '#6E7681',
    fontSize: 12,
    marginTop: 8,
    lineHeight: 18,
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#21262D',
  },
  switchLabel: {
    color: '#E6EDF3',
    fontSize: 14,
  },
  btn: {
    marginHorizontal: 16,
    marginBottom: 10,
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
  },
  btnPrimary: {
    backgroundColor: '#1F6FEB',
  },
  btnPrimaryText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  btnSecondary: {
    backgroundColor: '#161B22',
    borderWidth: 1,
    borderColor: '#30363D',
  },
  btnSecondaryText: {
    color: '#58A6FF',
    fontSize: 16,
    fontWeight: '600',
  },
  aboutRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#21262D',
  },
  aboutLabel: {
    color: '#8B949E',
    fontSize: 14,
  },
  aboutValue: {
    color: '#E6EDF3',
    fontSize: 14,
    fontWeight: '500',
  },
});
