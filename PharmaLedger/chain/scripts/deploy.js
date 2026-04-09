const hre = require("hardhat");

async function main() {
  const PharmaLedger = await hre.ethers.getContractFactory("PharmaLedger");
  const contract = await PharmaLedger.deploy();
  await contract.waitForDeployment();

  console.log("PharmaLedger deployed to:", await contract.getAddress());
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
