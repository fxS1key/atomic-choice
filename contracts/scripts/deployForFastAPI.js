// contracts/scripts/deployForFastAPI.js
// Deploys all contracts and writes addresses to fastapi/deployments.json
// Run: npx hardhat run scripts/deployForFastAPI.js --network localhost

const hre = require("hardhat");
const { ethers } = hre;
const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("═══════════════════════════════════════════════════════");
  console.log("  Atomic Choice → FastAPI Deployment");
  console.log("═══════════════════════════════════════════════════════");
  console.log(`  Deployer : ${deployer.address}`);
  console.log(`  Balance  : ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);
  console.log(`  Network  : ${hre.network.name}`);
  console.log("");

  // 1. PoseidonStub
  console.log("[1/4] Deploying PoseidonStub...");
  const PoseidonStub = await ethers.getContractFactory("PoseidonStub");
  const poseidon = await PoseidonStub.deploy();
  await poseidon.waitForDeployment();
  const poseidonAddr = await poseidon.getAddress();
  console.log(`      → ${poseidonAddr}`);

  // 2. VerifierStub
  console.log("[2/4] Deploying VerifierStub...");
  const VerifierStub = await ethers.getContractFactory("VerifierStub");
  const verifier = await VerifierStub.deploy();
  await verifier.waitForDeployment();
  const verifierAddr = await verifier.getAddress();
  console.log(`      → ${verifierAddr}  (TEST ONLY)`);

  // 3. Whitelist
  console.log("[3/4] Deploying Whitelist (depth=10)...");
  const Whitelist = await ethers.getContractFactory("Whitelist");
  const whitelist = await Whitelist.deploy(poseidonAddr, 10, deployer.address);
  await whitelist.waitForDeployment();
  const whitelistAddr = await whitelist.getAddress();
  console.log(`      → ${whitelistAddr}`);

  // 4. VotingFactory
  console.log("[4/4] Deploying VotingFactory...");
  const VotingFactory = await ethers.getContractFactory("VotingFactory");
  const factory = await VotingFactory.deploy(whitelistAddr, verifierAddr, deployer.address);
  await factory.waitForDeployment();
  const factoryAddr = await factory.getAddress();
  console.log(`      → ${factoryAddr}`);

  const deployment = {
    poseidon:  poseidonAddr,
    verifier:  verifierAddr,
    whitelist: whitelistAddr,
    factory:   factoryAddr,
    deployer:  deployer.address,
    chain_id:  31337,
    deployed_at: new Date().toISOString(),
  };

  // Save to contracts/deployments/
  const contractsOut = path.join(__dirname, "../deployments/localhost.json");
  fs.mkdirSync(path.dirname(contractsOut), { recursive: true });
  fs.writeFileSync(contractsOut, JSON.stringify(deployment, null, 2));

  // Save to FastAPI root (deployments.json)
  const fastapiOut = path.join(__dirname, "../../atomic-choice/deployments.json");
  if (fs.existsSync(path.dirname(fastapiOut))) {
    fs.writeFileSync(fastapiOut, JSON.stringify(deployment, null, 2));
    console.log(`\n  Saved → atomic-choice/deployments.json`);
  }

  console.log("\n═══════════════════════════════════════════════════════");
  console.log("  ✓ Done! Now start FastAPI:");
  console.log("    cd atomic-choice && uvicorn main:app --reload");
  console.log("═══════════════════════════════════════════════════════\n");
}

main().catch(e => { console.error(e); process.exit(1); });
