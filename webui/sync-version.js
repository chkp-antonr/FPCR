import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const pyprojectPath = path.resolve(__dirname, '../pyproject.toml');
const packageJsonPath = path.resolve(__dirname, 'package.json');

try {
    const pyprojectContent = fs.readFileSync(pyprojectPath, 'utf8');
    const versionMatch = pyprojectContent.match(/version\s*=\s*"([^"]+)"/);

    if (!versionMatch) {
        console.error('Could not find version in pyproject.toml');
        process.exit(1);
    }

    const version = versionMatch[1];

    const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));

    if (packageJson.version !== version) {
        console.log(`Syncing version: ${packageJson.version} -> ${version}`);
        packageJson.version = version;
        fs.writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n');
    } else {
        console.log(`Version already in sync: ${version}`);
    }
} catch (error) {
    console.error('Error syncing version:', error.message);
    process.exit(1);
}
