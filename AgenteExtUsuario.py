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

#facturas
facturas = []

# Datos del Agente

AgenteExtUsuario = Agent('AgenteExtUsuario',
                       agn.AgenteExtUsuario,
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
    message.add((search, RDF.type, Literal('Buscar_Productos')))
    if request.form['min_precio']:
        message.add((search, agn['min_precio'], Literal(int(request.form['min_precio']))))
    if request.form['max_precio']:
        message.add((search, agn['max_precio'], Literal(int(request.form['max_precio']))))
    if request.form['nombre']:
        message.add((search, agn.nombre, Literal(request.form['nombre'].lower())))
    if request.form['marca']:
        message.add((search, agn.tieneMarca, Literal(request.form['marca'].lower())))
    if request.form['tipo']:
        message.add((search, agn.tipo, Literal(request.form['tipo'].lower())))    
    asistente_compra = AgenteExtUsuario.directory_search(DirectoryAgent, agn.AsistenteCompra)    
    msg = build_message(
        message,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=asistente_compra.uri,
        msgcnt=mss_cnt,
        content=search
    )
    response = send_message(msg, asistente_compra.address)
    # Respuesta
    productos = []
    for item in response.subjects(RDF.type, None):
        if float(response.value(item, agn.numeroValoraciones)) == 0:
            valoracion = 0
        else:
            valoracion = float(response.value(item, agn.valoracionTotal)) / float(response.value(item, agn.numeroValoraciones))
        producto = dict(
            nombre = response.value(item, agn.nombre),
            peso = float(response.value(item, agn.peso)),
            precio = int(response.value(item, agn.precio)),
            tieneMarca = response.value(item, agn.tieneMarca),
            tipo = response.value(item, RDF.type),
            valoracion = valoracion
        )
        if (int(response.value(item, agn.numeroValoraciones)) == 0):
            producto['valoracion'] = 'N/D'
        producto['peso'] = float(int(producto['peso']*100)/100)
        productos.append(producto)
    return render_template('search_product.html', productos=productos)

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
    for nombre in request.form.getlist('nombre'):
        producto = agn[nombre]
        graph.add((producto, RDF.type, agn.product))
        graph.add((producto, agn.nombre, Literal(nombre)))            
    asistente_compra = AgenteExtUsuario.directory_search(DirectoryAgent, agn.AsistenteCompra)
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=asistente_compra.uri,
        msgcnt=mss_cnt,
        content=compra
    )
    newFactura = ""
    Pedido_en_marcha = ""
    numFact = len(facturas)
    send_message(message, asistente_compra.address)
    if(numFact != len(facturas)):
        newFactura = "Hay una nueva factura disponible"
    else:
        Pedido_en_marcha = "Pedido en marcha"
    return render_template('search_product.html', newFactura = newFactura, Pedido_en_marcha = Pedido_en_marcha)

@app.route("/factura", methods=['GET', 'POST'])
def factura():
    if request.method == 'GET':
        return render_template('factura.html', facturas=facturas)


@app.route("/comm")
def comm():    
    req = Graph().parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']    
    productos = []
    for producto in req.subjects(RDF.type, agn.product):
        producto_obj = dict(
            nombre = req.value(producto, agn.nombre),
            precio = req.value(producto, agn.precio),
            tieneMarca = str(req.value(producto, agn.tieneMarca))
        )
        productos.append(producto_obj)
    factura = dict(
        id_compra = int(req.value(content, agn.id_compra)),
        id_usuario = req.value(content, agn.id_usuario),
        direccion = req.value(content, agn.direccion),
        codigo_postal = req.value(content, agn.codigo_postal),
        fecha_compra = req.value(content, agn.fecha_compra),
        prioridad_envio = int(req.value(content, agn.prioridad_envio)),
        transportista = req.value(content, agn.transportista),
        fecha_recepcion = req.value(content, agn.fecha_recepcion),
        precio_total = int(req.value(content, agn.precio_total)),
        productos = productos
    )
    facturas.append(factura)
    return Graph().serialize(format='xml')

@app.route("/buscarProductosUsuario", methods=['GET', 'POST'])
def buscarProductosUsuario():

    if request.method == 'GET':
        return render_template('devolucion.html')

    global dsgraph
    global mss_cnt

    message = Graph()
    mss_cnt = mss_cnt + 1
    search = agn['search_query_' + str(mss_cnt)]
    id_usuario = request.form['id_usuario']
    message.add((search, agn['id_usuario'], Literal(id_usuario)))
    message.add((search, RDF.type, Literal('Buscar_Productos_Usuario')))    
    gestor_devoluciones = AgenteExtUsuario.directory_search(DirectoryAgent, agn.GestorDevoluciones)    
    msg = build_message(
        message,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=gestor_devoluciones.uri,
        msgcnt=mss_cnt,
        content=search
    )
    response = send_message(msg, gestor_devoluciones.address)

    logging.info('Productos del usuario:')

    productos_usuario = []
    for item in response.subjects(RDF.type, agn.product):
        nombre=str(response.value(subject=item, predicate=agn.nombre))
        logging.info(nombre)
        id_compra=(response.value(subject=item, predicate=agn.id_compra))
        productos_usuario.append(dict(
            nombre=nombre,
            id_compra=id_compra,
        ))
    return render_template('devolucion.html', productos_usuario=productos_usuario, id_usuario=id_usuario)


@app.route("/devolver", methods=['POST'])
def devolver():
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    logging.info('Devolver')
    logging.info(request.form['id_usuario'])
    logging.info(request.form['motivo'])
    logging.info(request.form['tarjeta_bancaria'])

    graph = Graph()
    devolucion = agn['devolucion_' + str(mss_cnt)]
    graph.add((devolucion, RDF.type, Literal('Devolver')))
    id_usuario = request.form['id_usuario']
    graph.add((devolucion, agn.id_usuario, Literal(id_usuario)))
    motivo = request.form['motivo']
    graph.add((devolucion, agn.motivo, Literal(motivo)))
    tarjeta = request.form['tarjeta_bancaria']
    graph.add((devolucion, agn.tarjeta, Literal(tarjeta)))

    i = 0
    logging.info('Productos a devolver:')
    for value in request.form.getlist('nombre'):
        value = value.split(';')
        nombre = value[0]
        id_compra = value[1]
        producto = agn[nombre]
        logging.info('Nombre: ' + nombre)
        logging.info('ID de la compra: ' + id_compra)
        #logging.info(Literal(request.form.getlist('id_compra')[i]))
        graph.add((devolucion, agn.producto, Literal(nombre)))
        graph.add((devolucion, agn.id_compra, Literal(id_compra)))
        #graph.add((devolucion, agn.id_compra, Literal(request.form.getlist('id_compra')[i])))
        i += 1    
    gestor_devoluciones = AgenteExtUsuario.directory_search(DirectoryAgent, agn.GestorDevoluciones) 
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=gestor_devoluciones.uri,
        msgcnt=mss_cnt,
        content=devolucion
    )
    result = send_message(message, gestor_devoluciones.address)

    resultado = ""
    for item in result.subjects(RDF.type, agn.respuesta):
        resultado=str(result.value(subject=item, predicate=agn.resultado))
        logging.info(resultado)

    return render_template('devolucion.html', respuesta=resultado)


@app.route("/feedback", methods=['POST', 'GET'])
def feedback():
    global mss_cnt

    if request.method == 'GET':
        return render_template('feedback.html')

    mss_cnt = mss_cnt + 1
    logging.info('Pedir Feedback')
    graph = Graph()
    compra = agn['feedback_' + str(mss_cnt)]
    graph.add((compra, RDF.type, Literal('Pedir_Feedback')))
    # id usario
    id_usuario = request.form['id_usuario']
    graph.add((compra, agn.id_usuario, Literal(id_usuario)))
    
    valorador = AgenteExtUsuario.directory_search(DirectoryAgent, agn.Valorador)
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=valorador.uri,
        msgcnt=mss_cnt,
        content=compra
    )
    response = send_message(message, valorador.address)

    logging.info('Productos del usuario:')

    productos_usuario = []
    for item in response.subjects(RDF.type, agn.product):
        nombre=str(response.value(subject=item, predicate=agn.nombre))
        logging.info(nombre)
        id_compra=str(response.value(subject=item, predicate=agn.id_compra))
        productos_usuario.append(dict(
            nombre=nombre,
            id_compra=id_compra,
        ))
    return render_template('feedback.html', productos_usuario=productos_usuario, id_usuario=id_usuario)


@app.route("/enviar_feedback", methods=['POST'])
def enviar_feedback():
    global mss_cnt

    logging.info('Enviar feedback')

    graph = Graph()
    devolucion = agn['enviar_feedback' + str(mss_cnt)]
    graph.add((devolucion, RDF.type, Literal('Enviar_Feedback')))

    i = 0
    for nombre in request.form.getlist('nombre'):
        logging.info(Literal(nombre))
        numero = str(Literal(request.form.getlist('valoracion')[i]))
        logging.info(numero)

        if str(numero) != ''  and float(numero) <= float(10) and float(numero) >= float(0):
            logging.info("xd")
            producto = agn[str(nombre) + '_' + str(i)]
            graph.add((producto, RDF.type, agn.product))
            graph.add((producto, agn.nombre, Literal(nombre)))
            graph.add((producto, agn.valoracion, Literal(request.form.getlist('valoracion')[i])))
        i += 1       

    valorador = AgenteExtUsuario.directory_search(DirectoryAgent, agn.Valorador) 
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=valorador.uri,
        msgcnt=mss_cnt,
        content=devolucion
    )
    send_message(message, valorador.address)
    return render_template('search_product.html')


@app.route("/recibir_recomendaciones", methods=['POST'])
def recibir_recomendaciones():
    global mss_cnt
    productos_usuario = []

    mss_cnt = mss_cnt + 1
    logging.info('Recibir recomendaciones')
    graph = Graph()
    recomendacion = agn['recomendacion_' + str(mss_cnt)]
    graph.add((recomendacion, RDF.type, Literal('Recibir_Recomendaciones')))
    # id usario
    id_usuario = request.form['id_usuario']
    graph.add((recomendacion, agn.id_usuario, Literal(id_usuario)))
    logging.info(id_usuario)
    
    valorador = AgenteExtUsuario.directory_search(DirectoryAgent, agn.Valorador)
    message = build_message(
        graph,
        perf=Literal('request'),
        sender=AgenteExtUsuario.uri,
        receiver=valorador.uri,
        msgcnt=mss_cnt,
        content=recomendacion
    )
    
    response = send_message(message, valorador.address)

    logging.info('Productos recomendados:')


    productos_recomendados = []
    for item in response.subjects(RDF.type, None):
        if float(response.value(item, agn.numeroValoraciones)) == 0:
            valoracion = 0
        else:
            valoracion = float(response.value(item, agn.valoracionTotal)) / float(response.value(item, agn.numeroValoraciones))
        nombre=str(response.value(item, agn.nombre))
        peso = float(response.value(item, agn.peso)),
        precio = int(response.value(item, agn.precio)),
        tieneMarca = (response.value(item, agn.tieneMarca)),
        tipo = str(response.value(item, RDF.type)),
        logging.info(nombre)
        productos_recomendados.append(dict(
            nombre=nombre,
            peso=peso,
            precio=precio,
            tieneMarca=str(tieneMarca),
            tipo=tipo,
            valoracion=valoracion,
        ))
    
    return render_template('feedback.html', productos_recomendados=productos_recomendados, id_usuario=id_usuario)


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
    AgenteExtUsuario.register_agent(DirectoryAgent)
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

