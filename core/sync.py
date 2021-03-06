from config import *
import os
import requests
import utils
import json
import glob
from chain import Chain
from block import Block
import nodes
from elastic import ElasticWrapper

mongo_conn = utils.MongoDBWrapper()
es = ElasticWrapper()

def sync_transactions():
    # print "Start syncing"
    # get local pending transactions
    # pending_transactions = mongo_conn.query_pending_transactions()
    # pending_txid = []
    # for tx in pending_transactions:
        # pending_txid.append(tx['txid'])
    # check other seed node pending transaction if not exist write to local
    NODES = nodes.get_list_node(mongo_conn)
    for node in NODES:
        endpoint = "%s%s" % (node, "/pending-transactions")
        try:
            r = requests.get(endpoint, timeout=5)
            data = r.json()['pending']
            for tx in data:
                if not mongo_conn.find_transaction_local(txid=tx['txid']):
                    mongo_conn.new_pending_transaction(txid=tx['txid'],
                                                       timestamp=tx['timestamp'],
                                                       data=tx['data'])
        except Exception as e:
            # print "Seed node %s not connected" % node
            print e
    return True
            

def sync_node():
    # get local node
    local_nodes = mongo_conn.query_confirm_node()
    node_ids = []
    for node in local_nodes:
        node_ids.append(node['uuid'])
    # check seed nodes if not exist append to list and write to local
    NODES = nodes.get_list_node(mongo_conn)
    for node in NODES:
        endpoint = "%s%s" % (node, "/confirm-nodes")
        try:
            r = requests.get(endpoint, timeout=5)
            data = r.json()['nodes']
            for n in data:
                if n['uuid'] not in node_ids:
                    del n['_id']
                    mongo_conn.register_node(n)
                    node_ids.append(n['uuid'])
        except requests.exceptions.ConnectionError:
            print "Node %s is not connected" % node
    return True

def sync_local(sync_es=False):
    local_chain = Chain([])
    if os.path.exists(CHAINDATA_DIR):
        for filepath in sorted(glob.glob(os.path.join(CHAINDATA_DIR, '*.json'))):
            with open(filepath, 'r') as block_file:
                try:
                    block_info = json.load(block_file)
                except:
                    raise Exception("block error")
                if sync_es:
                    es.insert_document(block_info)
                local_block = Block(block_info)
                local_chain.add_block(local_block)
    return local_chain

def sync_overall(save=False, sync_es=False):
    local_chain = sync_local(sync_es)
    NODES = nodes.get_list_node(mongo_conn)
    for peer in NODES:
        endpoint = peer + '/blockchain'
        try:
            r = requests.get(endpoint, timeout=5)
            chain_data = r.json()
            peer_blocks = [Block(block_dict) for block_dict in chain_data]
            peer_chain = Chain(peer_blocks)
            # check valid , if valid and longer, sync local
            if peer_chain.is_valid() and len(peer_chain) > len(local_chain):
                ## insert new block to elasticsearch
                ## find a new block
                ## m is length of local_chains 
                ## n la so block moi can them 
                m = len(local_chain)
                n = len(peer_chain) - len(local_chain)

                peer_blocks = peer_chain.blocks
                local_blocks = local_chain.blocks
                for i in range(0, n):
                    block = local_blocks[i + m]
                    block_dict = block.dict()
                    es.insert_document(block_dict)
                local_chain = peer_chain
        except Exception as e:
            pass
    if save:
        local_chain.self_save()
    return local_chain


def sync():
    sync_overall(save=True)

