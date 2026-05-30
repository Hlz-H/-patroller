import { Platform } from 'react-native';
import * as ExpoNotifications from 'expo-notifications';
import * as Device from 'expo-device';

// Configure notification handler
ExpoNotifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export interface NotificationPermission {
  granted: boolean;
  error?: string;
}

/**
 * Request push notification permissions from the user.
 * On Android 10+, this shows a runtime permission dialog.
 * On iOS, this requests APNS authorization.
 */
export async function requestPermissions(): Promise<NotificationPermission> {
  try {
    if (!Device.isDevice) {
      // Running in simulator/emulator — notifications won't work
      return { granted: false, error: 'Simulator detected, notifications unavailable' };
    }

    const { status: existingStatus } = await ExpoNotifications.getPermissionsAsync();
    let finalStatus = existingStatus;

    if (existingStatus !== 'granted') {
      const { status } = await ExpoNotifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') {
      return { granted: false, error: 'Notification permission denied' };
    }

    // Android: create default notification channel
    if (Platform.OS === 'android') {
      await ExpoNotifications.setNotificationChannelAsync('default', {
        name: 'Default',
        importance: ExpoNotifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#58A6FF',
      });
    }

    return { granted: true };
  } catch (err) {
    return { granted: false, error: String(err) };
  }
}

/**
 * Schedule a local notification (for testing or offline alerts).
 */
export async function scheduleLocalNotification(
  title: string,
  body: string,
  data?: Record<string, unknown>
): Promise<string | undefined> {
  try {
    const id = await ExpoNotifications.scheduleNotificationAsync({
      content: {
        title,
        body,
        data: data || {},
        sound: 'default',
      },
      trigger: null, // immediate
    });
    return id;
  } catch (err) {
    console.error('Failed to schedule notification:', err);
    return undefined;
  }
}

/**
 * Get the Expo push token for remote push notifications.
 * Returns null if not available (simulator or no permission).
 */
export async function getExpoPushToken(): Promise<string | null> {
  try {
    const { status } = await ExpoNotifications.getPermissionsAsync();
    if (status !== 'granted') return null;

    const token = await ExpoNotifications.getExpoPushTokenAsync();
    return token.data;
  } catch (err) {
    console.error('Failed to get push token:', err);
    return null;
  }
}

/**
 * Add a listener for incoming notifications while app is foregrounded.
 * Returns a subscription that should be cleaned up on unmount.
 */
export function addNotificationListener(
  handler: (notification: ExpoNotifications.Notification) => void
): ExpoNotifications.EventSubscription {
  return ExpoNotifications.addNotificationReceivedListener(handler);
}

/**
 * Add a listener for notification response (user tapped on notification).
 * Returns a subscription that should be cleaned up on unmount.
 */
export function addNotificationResponseListener(
  handler: (response: ExpoNotifications.NotificationResponse) => void
): ExpoNotifications.EventSubscription {
  return ExpoNotifications.addNotificationResponseReceivedListener(handler);
}
