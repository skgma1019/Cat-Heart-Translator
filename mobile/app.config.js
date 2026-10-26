module.exports = {
  expo: {
    name: '냥심 번역기', slug: 'cat-heart-translator', owner: 'skgma1019', version: '1.0.0',
    orientation: 'portrait', android: { package: 'com.catheart.translator' },
    plugins: ['expo-document-picker'],
    extra: { apiUrl: process.env.EXPO_PUBLIC_API_URL || 'https://cat-heart-translator-api.onrender.com', eas: { projectId: '58ec3d2d-2531-4e32-ba8c-3e364673f30f' } },
  },
};
