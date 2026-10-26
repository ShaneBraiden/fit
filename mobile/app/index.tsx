import { Ionicons } from '@expo/vector-icons';
import { Redirect } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { Button, Card, Chip, Field, H2, P, Row, Screen } from '../components/ui';
import { AuthResult, request, SignupRequest } from '../lib/api';
import { useSession } from '../lib/session';
import { space, type, useTheme } from '../lib/theme';

/** Sign in, or create an account with the body measurements the predictions need. */
export default function Welcome() {
  const t = useTheme();
  const { ready, token, signIn, apiUrl } = useSession();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [gender, setGender] = useState<'F' | 'M' | null>(null);
  const [age, setAge] = useState('');
  const [height, setHeight] = useState('');
  const [weight, setWeight] = useState('');
  const [restingHr, setRestingHr] = useState('');
  const [vo2, setVo2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ready) return <View style={{ flex: 1, backgroundColor: t.page, justifyContent: 'center' }}><ActivityIndicator color={t.accent} /></View>;
  if (token) return <Redirect href="/(tabs)/today" />;

  const num = (s: string) => (s.trim() === '' ? null : Number(s.replace(',', '.')));
  const submit = async () => {
    setError(null);
    if (!email.trim() || !password) return setError('Enter your email and password.');
    let path = '/api/auth/login';
    let body: unknown = { email, password };
    if (mode === 'signup') {
      const a = num(age), h = num(height), w = num(weight);
      if (!name.trim() || !gender || a == null || h == null || w == null) return setError('Fill in your name, sex, age, height and weight.');
      if (password.length < 8) return setError('Use a password of at least 8 characters.');
      const req: SignupRequest = { email, password, name: name.trim(), gender, age: Math.round(a), height_cm: h, weight_kg: w,
        resting_hr: num(restingHr), vo2max: num(vo2) };
      path = '/api/auth/signup';
      body = req;
    }
    setBusy(true);
    try {
      const r = await request<AuthResult>(apiUrl, path, { body });
      signIn(r.token, r.account);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <View style={{ alignItems: 'center', marginTop: space.lg, marginBottom: space.sm }}>
          <View style={{ width: 56, height: 56, borderRadius: 16, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="pulse" size={30} color="#fff" />
          </View>
          <Text style={[type.hero, { color: t.text, marginTop: space.md }]}>FitMine</Text>
          <P muted style={{ textAlign: 'center', marginTop: 4 }}>Track your workouts and see your fitness level, training style and what to try next.</P>
        </View>

        <Row gap={space.sm} style={{ justifyContent: 'center' }}>
          <Chip label="Sign in" on={mode === 'login'} onPress={() => { setMode('login'); setError(null); }} />
          <Chip label="Create account" on={mode === 'signup'} onPress={() => { setMode('signup'); setError(null); }} />
        </Row>

        <Card>
          <View style={{ gap: space.md }}>
            {mode === 'signup' && <Field label="Name" value={name} onChangeText={setName} autoComplete="name" textContentType="name" />}
            <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoCorrect={false} keyboardType="email-address"
              autoComplete="email" textContentType="emailAddress" />
            <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none"
              autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} onSubmitEditing={mode === 'login' ? submit : undefined}
              hint={mode === 'signup' ? 'At least 8 characters.' : undefined} />
          </View>
        </Card>

        {mode === 'signup' && (
          <Card>
            <H2>About you</H2>
            <P muted small style={{ marginBottom: space.md }}>Used to estimate your fitness level and calories. You can change these later.</P>
            <P small muted style={{ marginBottom: 6 }}>Sex</P>
            <Row gap={space.sm} style={{ marginBottom: space.md }}>
              <Chip label="Female" on={gender === 'F'} onPress={() => setGender('F')} />
              <Chip label="Male" on={gender === 'M'} onPress={() => setGender('M')} />
            </Row>
            <Row gap={space.md} wrap>
              <Field label="Age" value={age} onChangeText={setAge} keyboardType="number-pad" />
              <Field label="Height (cm)" value={height} onChangeText={setHeight} keyboardType="decimal-pad" />
              <Field label="Weight (kg)" value={weight} onChangeText={setWeight} keyboardType="decimal-pad" />
            </Row>
            <Row gap={space.md} wrap style={{ marginTop: space.md }}>
              <Field label="Resting heart rate" value={restingHr} onChangeText={setRestingHr} keyboardType="number-pad" hint="Optional, bpm" />
              <Field label="VO2max" value={vo2} onChangeText={setVo2} keyboardType="decimal-pad" hint="Optional, from your watch" />
            </Row>
          </Card>
        )}

        {error && <P style={{ color: t.criticalInk }}>{error}</P>}
        <Button label={mode === 'login' ? 'Sign in' : 'Create account'} icon={mode === 'login' ? 'log-in-outline' : 'person-add-outline'}
          onPress={submit} busy={busy} />
      </Screen>
    </KeyboardAvoidingView>
  );
}
