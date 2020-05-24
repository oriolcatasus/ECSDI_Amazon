# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
import socket
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request, render_template

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants

# Configuration stuff
hostname = '127.0.1.1'
port = 9001

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

AgentExtUser = Agent('AgentExtUser',
                       agn.AgentExtUser,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/", methods=['GET', 'POST'])
def comunicacion():
    """
    Entrypoint de comunicacion
    """
    if request.method == 'GET':
        return render_template('search_product.html')

    global dsgraph
    global mss_cnt

    message = Graph()
    mss_cnt = mss_cnt + 1
    search = agn['search_query_' + str(mss_cnt)]
    if request.form['min_precio']:
        message.add((search, agn['min_precio'], Literal(int(request.form['min_precio']))))
    if request.form['max_precio']:
        message.add((search, agn['max_precio'], Literal(int(request.form['max_precio']))))
    message.add((search, RDF.type, Literal('Buscar_Productos')))    
    AtencionAlCliente = AgentExtUser.directory_search(DirectoryAgent, agn.AtencionAlCliente)    
    msg = build_message(
        message,
        perf=Literal('request'),
        sender=AgentExtUser.uri,
        receiver=AtencionAlCliente.uri,
        msgcnt=mss_cnt,
        content=search
    )
    response = send_message(msg, AtencionAlCliente.address)

    productos = []
    for item in response.subjects(RDF.type, agn.product):
        nombre=str(response.value(subject=item, predicate=agn.nombre))
        peso=str(response.value(subject=item, predicate=agn.peso))
        precio=str(response.value(subject=item, predicate=agn.precio))
        tieneMarca=str(response.value(subject=item, predicate=agn.tieneMarca))
        productos.append(dict(
            nombre=nombre,
            peso=peso,
            precio=precio,
            tieneMarca=tieneMarca
        ))

    return render_template('search_product.html', productos=productos)
    pass

@app.route("/comprar", methods=['POST'])
def comprar():
    global mss_cnt

    mss_cnt = mss_cnt + 1
    logging.info('Comprar')
    graph = Graph()
    compra = agn['pedido_' + str(mss_cnt)]
    graph.add((compra, RDF.type, Literal('Comprar')))
    # Codigo postal
    codigo_postal = request.form['codigo_postal']
    graph.add((compra, agn.codigo_postal, Literal(codigo_postal)))
    # Direccion de envio
    direccion = request.form['direccion']
    graph.add((compra, agn.direccion, Literal(direccion)))
    # id usario
    id_usuario = request.form['id_usuario']
    graph.add((compra, agn.id_usuario, Literal(id_usuario)))
    # tarjeta bancaria
    tarjeta_bancaria = request.form['tarjeta_bancaria']
    graph.add((compra, agn.tarjeta_bancaria, Literal(tarjeta_bancaria)))
    # Prioridad
    prioridad_envio = int(request.form['prioridad'])
    graph.add((compra, agn.prioridad_envio, Literal(prioridad_envio)))
    # Productos
    for nombre in request.form:
        if nombre.startswith('nombre_'):
            producto = agn[nombre]
            graph.add((producto, RDF.type, agn.product))
            graph.add((producto, agn.nombre, Literal(nombre)))
    atencion_al_cliente = AgentExtUser.directory_search(DirectoryAgent, agn.AtencionAlCliente)
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AgentExtUser.uri,
        receiver=atencion_al_cliente.uri,
        msgcnt=mss_cnt,
        content=compra
    )
    send_message(message, atencion_al_cliente.address)
    return render_template('search_product.html')

@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AgentExtUser.register_agent(DirectoryAgent)
    #comunicacion()
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


