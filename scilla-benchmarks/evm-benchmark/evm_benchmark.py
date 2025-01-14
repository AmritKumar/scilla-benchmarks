import re
import os
import time
import binascii
import subprocess
from eth_abi import encode_abi
from utils import keccak256, generate_address,\
    get_addresses, get_directory_size
from db import calculate_all_db_key_value_sizes
import uuid
import random
import shutil
import time
from statistics import median, mean

from evm_tools import measure_evm_data_size, measure_gas_cost, solc_compile_contract,\
    get_value, generate_params, deploy_contract, perform_transaction, evm_data_dir,\
    contracts_dir, get_current_root_hash, evm_start_data_dir
from benchmark_plans import contracts_benchmark_plans, SENDER_ADDRESS


def setup_test(setup_plans, contract_address):
    for setup_plan in setup_plans:
        perform_transaction(contract_address, setup_plan)


def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


def run_tests(bytecode, contract_plan):
    tests = contract_plan['tests']

    for test_plan in tests:
        test_name = test_plan['test_name']

        setup_plans = test_plan.get('setup_transactions')
        if setup_plans:
            print('Setting up `{}`...'.format(test_name))
            if callable(setup_plans):
                setup_plans()
            else:
                setup_test(setup_plans, address)
            print('Finished setting up `{}`.'.format(test_name))

        all_transactions = test_plan['transactions']
        matching_txns = filter(
            lambda tx: tx['function'].name == test_name, all_transactions)
        iterations = len(list(matching_txns))
        print('Running {} iterations of `{}` function'.format(
            iterations, test_name))

        addr_copy = None

        def reset_contract(new_contract=False):
            # if new_contract, create dir in evm_data_start_dir
            # copy it over to evm_data_dir
            # if not new_contract, just copy it over

            if new_contract:
                if os.path.isdir(evm_start_data_dir):
                    shutil.rmtree(evm_start_data_dir)
                if os.path.isdir(evm_data_dir):
                    shutil.rmtree(evm_data_dir)
                address = deploy_contract(
                    bytecode, *contract_plan['constructor'], dirname=evm_start_data_dir)
                copytree(evm_start_data_dir, evm_data_dir)
                return address
            else:
                if os.path.isdir(evm_data_dir):
                    shutil.rmtree(evm_data_dir)
                copytree(evm_start_data_dir, evm_data_dir)
                return addr_copy

        total_times = []
        execution_times = []
        init_times = []
        io_times = []
        iteration_counter = 0
        address = reset_contract(new_contract=True)
        addr_copy = address

        for txn_plan in all_transactions:
            is_matching_test = txn_plan['function'].name == test_name

            if is_matching_test:
                address = reset_contract(new_contract=False)
                if iteration_counter == 0:
                    print('Contract deployed at:', address)
                    print('Contract bytecode size: {} bytes'.format(
                        len(bytecode.encode('utf-8'))))
                    # print('Total gas cost:', measure_gas_cost(bytecode))
                    db_size, key_count = calculate_all_db_key_value_sizes()
                    print('Initial EVM database size: {:,} bytes'.format(
                        db_size))

                iteration_counter += 1
                if iteration_counter % 10 == 0:
                    print('Ran {} iterations'.format(iteration_counter))

            total_time, exec_time, init_time, io_time = perform_transaction(
                address, txn_plan)

            # there may be some transactions interleaved
            # so we only count the ones with the matching function name
            if is_matching_test:
                total_times.append(total_time)
                execution_times.append(exec_time)
                init_times.append(init_time)
                io_times.append(io_time)

        print('Ran {} iterations of {} function'.format(
            iterations, test_plan['test_name']))
        db_size, key_count = calculate_all_db_key_value_sizes()
        print('New database size: {:,} bytes'.format(
            db_size))
        print('Median total time: {0:.6f} ms'.format(
            median(total_times)))
        print('Median execution time: {0:.6f} ms'.format(
            median(execution_times)))
        print('Mean execution time: {0:.6f} ms'.format(
            mean(execution_times)))
        print('Median init time: {0:.6f} ms'.format(
            median(init_times)))
        print('Median IO time: {0:.6f} ms'.format(
            median(io_times)))
        print()


def populate_evm_state(address, transactions):
    print(
        '\nPopulating EVM state with {} transactions...'.format(
            len(transactions)))
    for index, txn_plan in enumerate(transactions):
        if index % 10 == 0:
            print('Executed {} transactions'.format(index))
        perform_transaction(address, txn_plan)


def run_benchmark(contract_plan):
    # clear the EVM data directory
    if os.path.isdir(evm_data_dir):
        shutil.rmtree(evm_data_dir)

    contract_path = os.path.join(
        contracts_dir, contract_plan['contract_filename'])
    bytecode = solc_compile_contract(
        contract_path, contract_plan['contract_name'])

    with open(contract_path) as f:
        source_code_len = len(f.read())
        print('{} source size is:'.format(
            contract_plan['contract_name']), source_code_len)

    run_tests(bytecode, contract_plan)
    db_size, key_count = calculate_all_db_key_value_sizes()
    print('Final EVM database size: {:,} bytes'.format(
        db_size))


def main():
    for plan in contracts_benchmark_plans:
        run_benchmark(plan)


if __name__ == '__main__':
    main()
