module.exports = {
  expo: {
    name: '냥심 번역기', slug: 'cat-heart-translator', version: '1.0.0',
    orientation: 'portrait', android: { package: 'com.catheart.translator' },
    plugins: ['expo-document-picker'],
    extra: { apiUrl: process.env.EXPO_PUBLIC_API_URL || 'https://cat-heart-translator-api.onrender.com' },
  },
};
