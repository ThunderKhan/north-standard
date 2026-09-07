// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {NorthStandardSettlement} from "../src/NorthStandardSettlement.sol";

interface VmDeploy {
    function envUint(string calldata key) external returns (uint256 value);
    function startBroadcast(uint256 privateKey) external;
    function stopBroadcast() external;
}

contract DeployNorthStandardSettlement {
    VmDeploy private constant vm = VmDeploy(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (NorthStandardSettlement settlement) {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        vm.startBroadcast(deployerPrivateKey);
        settlement = new NorthStandardSettlement();
        vm.stopBroadcast();
    }
}
